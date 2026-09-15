from decimal import Decimal
import json
import re
from typing import Protocol, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Assumption,
    BusinessCaseProject,
    BusinessCaseVersion,
    CitationSnapshot,
    EvidenceChunk,
    FinancialScenario,
    GenerationRun,
    QualityReport,
    SourceDocument,
)
from app.repositories.generation import GenerationRepository
from app.repositories.rules import RuleRepository
from app.schemas import GenerationCreate
from app.services.financial import FinancialEngine, FinancialMetrics
from app.services.llm_provider import OpenAICompatibleClient, OpenAICompatibleCritic, OpenAICompatibleGenerator
from app.services.rules import REQUIRED_HEADINGS


class LLMProvider(Protocol):
    def compose(self, section_id: str, title: str, facts: dict[str, object]) -> str: ...


class QualityCritic(Protocol):
    def evaluate(self, sections: list[dict[str, object]], rules: list[dict[str, object]]) -> list[dict[str, str]]: ...


class MockLLMProvider:
    def compose(self, section_id: str, title: str, facts: dict[str, object]) -> str:
        project = str(facts["project"])
        decision = str(facts["decision"])
        problem = str(facts["problem"])
        solution = str(facts.get("solution") or "la alternativa recomendada por validar")
        metrics = facts["metrics"]
        evidence_note = str(facts["evidence_note"])
        interview = facts.get("interview_context", {})
        interview_note = "; ".join(f"{key}: {value}" for key, value in cast(dict[str, str], interview).items()) if isinstance(interview, dict) else ""
        content = {
            "cover": f"{project}. Propietario: {facts['sponsor']}. Versión {facts['version']}, fecha {facts['date']}.",
            "executive_summary": f"Se solicita {decision}. El caso responde a: {problem}. La solución propuesta es {solution}. La evaluación financiera base es {metrics}. {evidence_note}",
            "problem_opportunity": f"Situación a resolver: {problem}. No actuar mantiene el impacto descrito y requiere cuantificación adicional cuando la evidencia no la aporta. {evidence_note}",
            "strategic_alignment": f"La iniciativa debe vincularse con objetivos medibles de corto, mediano y largo plazo. Audiencia decisora: {facts['audience']}. Contexto de entrevista: {interview_note or 'Dato requerido'}. {evidence_note}",
            "scope_assumptions": f"Incluye la entrega descrita en el brief. La entrevista aportó: {interview_note or 'Dato requerido'}. Los recursos y dependencias deben confirmarse antes de comprometer fechas.",
            "alternatives": f"A — No hacer nada: conserva el problema. B — Solución parcial: reduce alcance y beneficio. C — Solución propuesta: {solution}. Las tres opciones deben validarse con costos, tiempo, riesgo y valor homogéneos.",
            "recommendation": f"Se recomienda evaluar y avanzar con {solution}, condicionado a validar los datos requeridos y controles señalados. Decisión solicitada: {decision}.",
            "benefits": "Los beneficios financieros se reflejan en los flujos del escenario base. Los beneficios no financieros y sus propietarios requieren confirmación explícita.",
            "financial_analysis": f"Resultados calculados por código para el escenario base: {metrics}. Los importes conservan la moneda y el horizonte del proyecto.",
            "sensitivity": str(facts["scenario_summary"]),
            "risks": "Riesgos a gobernar: financieros, operativos, tecnológicos, privacidad, seguridad y cumplimiento. Cada responsable y contingencia debe confirmarse.",
            "implementation_plan": "Ruta preliminar: preparación, ejecución, adopción y realización de beneficios. Fechas, hitos, recursos, responsables y KPIs deben aprobarse antes de iniciar.",
            "change_management": "Se requiere identificar grupos afectados, comunicación, formación, soporte y transferencia al modelo operativo estable.",
            "kpis": "Cada beneficio material requiere indicador, fórmula, línea base, meta, frecuencia y propietario. Los valores ausentes quedan como Dato requerido.",
            "conclusion": f"Se solicita al comité resolver: {decision}. Próximo paso: confirmar supuestos críticos, responsables y autorización de recursos.",
            "sources_annexes": f"Se conservaron {facts['citation_count']} referencias históricas y el snapshot de reglas de esta versión.",
        }
        return content.get(section_id, f"{title}: Dato requerido.")


class DeterministicQualityCritic:
    def evaluate(self, sections: list[dict[str, object]], rules: list[dict[str, object]]) -> list[dict[str, str]]:
        return [
            {"section_id": str(section["section_id"]), "criterion": heading, "result": "cumple", "explanation": "Validado por el crítico determinista contra la regla publicada."}
            for section in sections for heading in REQUIRED_HEADINGS
        ]


class GenerationService:
    def __init__(self, session: Session, provider: LLMProvider | None = None, critic: QualityCritic | None = None) -> None:
        self.session = session
        self.repository = GenerationRepository(session)
        settings = get_settings()
        if provider is not None:
            self.provider = provider
            self.critic = critic or DeterministicQualityCritic()
        elif settings.use_mocks:
            self.provider = MockLLMProvider()
            self.critic = DeterministicQualityCritic()
        elif settings.llm_provider == "openai_compatible":
            client = OpenAICompatibleClient(
                base_url=settings.llm_base_url,
                api_key_file=settings.llm_api_key_file,
                api_style=settings.llm_api_style,
                timeout_seconds=settings.llm_timeout_seconds,
                max_output_tokens=settings.llm_max_output_tokens,
                ca_bundle=settings.llm_ca_bundle,
                user_agent=settings.llm_user_agent,
                originator=settings.llm_originator,
            )
            self.provider = OpenAICompatibleGenerator(client, settings.llm_generator_model)
            self.critic = critic or OpenAICompatibleCritic(client, settings.llm_critic_model or settings.llm_generator_model)
        else:
            raise RuntimeError("LLM_PROVIDER must be `openai_compatible` when mocks are disabled")
        self.max_attempts = settings.llm_max_retries + 1
        self.financial = FinancialEngine()

    def generate(
        self,
        project: BusinessCaseProject,
        payload: GenerationCreate,
        source_version: BusinessCaseVersion | None = None,
        target_section: str | None = None,
        idempotency_key: str | None = None,
    ) -> GenerationRun:
        if idempotency_key:
            existing = self.repository.find_idempotent_run(project.id, idempotency_key)
            if existing is not None:
                return existing
        run = self.repository.create_run(GenerationRun(project_id=project.id, status="preparing", progress=10, idempotency_key=idempotency_key))
        try:
            version_number = self.repository.next_version_number(project.id)
            rules = RuleRepository(self.session).effective_rules()
            global_rule = next(version for definition, version in rules if definition.section_id == "global")
            citations = self._citation_data(project.id)
            scenarios = self._scenarios(project, payload)
            base_metrics = scenarios[1][2]
            facts: dict[str, object] = {
                "project": project.name,
                "document_kind": payload.document_kind,
                "document_label": "blueprint" if payload.document_kind == "blueprint" else "business case",
                "project_type": payload.project_type,
                "organization": project.organization,
                "responsible_area": payload.responsible_area,
                "sponsor": payload.sponsor,
                "decision": payload.decision,
                "problem": payload.problem,
                "solution": payload.solution,
                "audience": payload.audience,
                "version": version_number,
                "date": run.created_at.date().isoformat(),
                "metrics": self._metrics_text(project.currency, base_metrics),
                "scenario_summary": self._scenario_text(project.currency, scenarios),
                "evidence_note": f"Sustento disponible: {len(citations)} cita(s)." if citations else "Dato requerido: evidencia documental incluida.",
                "citation_count": len(citations),
                "evidence": [{"document": item["document_name"], "locator": item["locator"], "excerpt": item["excerpt"]} for item in citations[:12]],
                "interview_context": payload.interview_context,
            }
            citation_ids = [item["id"] for item in citations]
            previous_sections = {
                section["section_id"]: section for section in json.loads(source_version.content_json)["sections"]
            } if source_version is not None and target_section is not None else {}
            sections: list[dict[str, object]] = []
            for definition, _rule in rules:
                if definition.section_id == "global":
                    continue
                if definition.section_id in previous_sections and definition.section_id not in {target_section, "cover"}:
                    sections.append(previous_sections[definition.section_id])
                    continue
                sections.append({
                    "section_id": definition.section_id,
                    "title": definition.title,
                    "content": self._compose_with_retry(definition.section_id, definition.title, {**facts, "global_rule_markdown": global_rule.markdown, "section_rule_markdown": _rule.markdown, "section_rule_version": _rule.version_number}),
                    "citation_ids": citation_ids[:3],
                    "labels": [] if citations else ["Dato requerido"],
                })
            findings = self._contradiction_findings(citations)
            if not citations:
                findings.append({"dimension": "trazabilidad", "severity": "warning", "section": "global", "message": "No existe evidencia incluida; las afirmaciones quedan etiquetadas.", "action": "Adjuntar o incluir fuentes."})
            content = {"table_of_contents": [{"ordinal": index + 1, "section_id": section["section_id"], "title": section["title"]} for index, section in enumerate(sections)], "sections": sections}
            rules_snapshot = [{"section_id": definition.section_id, "title": definition.title, "version": version.version_number, "markdown": version.markdown} for definition, version in rules]
            section_rules = [item for item in rules_snapshot if item["section_id"] != "global"]
            compliance = self._evaluate_with_retry(sections, section_rules)
            sections, compliance = self._repair_noncompliant_sections(
                sections,
                compliance,
                section_rules,
                rules,
                facts,
            )
            content = {
                "table_of_contents": content["table_of_contents"],
                "sections": sections,
            }
            unresolved = [item for item in compliance if item["result"] == "no cumple"]
            for item in unresolved:
                findings.append({
                    "dimension": "cumplimiento de reglas",
                    "severity": "warning",
                    "section": item["section_id"],
                    "message": item["explanation"],
                    "action": f"Resolver el criterio: {item['criterion']}.",
                })
            version = BusinessCaseVersion(
                project_id=project.id,
                version_number=version_number,
                status="ready",
                content_json=json.dumps(content, ensure_ascii=False),
                input_snapshot_json=payload.model_dump_json(),
                rules_snapshot_json=json.dumps(rules_snapshot, ensure_ascii=False),
            )
            version.scenarios = [FinancialScenario(name=name, inputs_json=json.dumps(inputs), metrics_json=json.dumps(metrics.as_dict())) for name, inputs, metrics in scenarios]
            version.quality_report = QualityReport(score=max(0, (100 if citations else 92) - 8 * len(self._contradiction_findings(citations)) - 4 * len(unresolved)), findings_json=json.dumps(findings, ensure_ascii=False), compliance_json=json.dumps(compliance, ensure_ascii=False))
            version.citations = [CitationSnapshot(**item) for item in citations]
            if not citations:
                version.assumptions = [Assumption(section_id="global", text="La evidencia documental está pendiente.", impact="Reduce la confianza y obliga a validar afirmaciones materiales.")]
            self.repository.save_version(version, run)
            project.status = "generated"
            self.session.commit()
            return run
        except Exception as error:
            self.session.rollback()
            persisted_run = self.repository.get_run(run.id)
            if persisted_run is not None:
                self.repository.fail_run(persisted_run, "generation_failed", str(error))
            raise

    def regenerate(self, version: BusinessCaseVersion, section_id: str | None) -> GenerationRun:
        payload = GenerationCreate.model_validate_json(version.input_snapshot_json)
        if section_id:
            snapshot = json.loads(version.content_json)
            if section_id not in {section["section_id"] for section in snapshot["sections"]}:
                raise ValueError("Section not found in source version")
        return self.generate(version.project, payload, version, section_id)

    def _compose_with_retry(self, section_id: str, title: str, facts: dict[str, object]) -> str:
        last_error: Exception | None = None
        for _attempt in range(self.max_attempts):
            try:
                content = self.provider.compose(section_id, title, facts)
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("Provider returned an invalid section")
                return content.strip()
            except (TimeoutError, ValueError) as error:
                last_error = error
        raise RuntimeError(f"Provider failed after limited retries: {last_error}") from last_error

    def _evaluate_with_retry(self, sections: list[dict[str, object]], rules: list[dict[str, object]]) -> list[dict[str, str]]:
        last_error: Exception | None = None
        for _attempt in range(self.max_attempts):
            try:
                compliance = self.critic.evaluate(sections, rules)
                if not compliance:
                    raise ValueError("Critic returned no compliance results")
                return compliance
            except (TimeoutError, ValueError) as error:
                last_error = error
        raise RuntimeError(f"Critic failed after limited retries: {last_error}") from last_error

    def _repair_noncompliant_sections(
        self,
        sections: list[dict[str, object]],
        compliance: list[dict[str, str]],
        rules_snapshot: list[dict[str, object]],
        effective_rules: list[tuple[object, object]],
        facts: dict[str, object],
    ) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
        failures: dict[str, list[dict[str, str]]] = {}
        for item in compliance:
            if item["result"] == "no cumple":
                failures.setdefault(item["section_id"], []).append(item)
        if not failures:
            return sections, compliance

        rules_by_section = {
            definition.section_id: version
            for definition, version in effective_rules
            if definition.section_id != "global"
        }
        global_rule = next(version for definition, version in effective_rules if definition.section_id == "global")
        repaired: list[dict[str, object]] = []
        for section in sections:
            section_id = str(section["section_id"])
            feedback = failures.get(section_id)
            rule = rules_by_section.get(section_id)
            if not feedback or rule is None:
                repaired.append(section)
                continue
            revised = dict(section)
            revised["content"] = self._compose_with_retry(
                section_id,
                str(section["title"]),
                {
                    **facts,
                    "global_rule_markdown": global_rule.markdown,
                    "section_rule_markdown": rule.markdown,
                    "section_rule_version": rule.version_number,
                    "current_content": section["content"],
                    "compliance_feedback": feedback,
                },
            )
            repaired.append(revised)
        return repaired, self._evaluate_with_retry(repaired, rules_snapshot)

    @staticmethod
    def _contradiction_findings(citations: list[dict[str, str | None]]) -> list[dict[str, str]]:
        costs: list[tuple[str, str]] = []
        explicit_cost = re.compile(
            r"\bcosto\s+(?:autorizado|propuesto|total|estimado)\s*:\s*(?:MXN\s*)?([0-9]+(?:[.,][0-9]+)?)",
            re.IGNORECASE,
        )
        for citation in citations:
            excerpt = citation["excerpt"] or ""
            match = explicit_cost.search(excerpt)
            if match:
                costs.append((citation["document_name"] or "fuente", match.group(1).replace(",", ".")))
        distinct = {value for _name, value in costs}
        if len(distinct) < 2:
            return []
        evidence = "; ".join(f"{name}: {value}" for name, value in costs)
        return [{"dimension": "consistencia", "severity": "critical", "section": "financial_analysis", "message": "Las fuentes contienen costos incompatibles y requieren resolución humana.", "evidence": evidence, "action": "Confirmar el costo autorizado sin resolver la contradicción silenciosamente."}]

    def _citation_data(self, project_id: str) -> list[dict[str, str | None]]:
        statement = select(EvidenceChunk, SourceDocument).join(SourceDocument).where(SourceDocument.project_id == project_id, SourceDocument.included.is_(True), EvidenceChunk.included.is_(True)).order_by(SourceDocument.created_at, EvidenceChunk.ordinal)
        citations: list[dict[str, str | None]] = []
        for chunk, document in self.session.execute(statement):
            locator = f"página {chunk.page_number}" if chunk.page_number else f"{chunk.sheet_name} {chunk.cell_range}" if chunk.sheet_name else f"fragmento {chunk.ordinal + 1}"
            citations.append({"id": str(uuid4()), "document_id": document.id, "chunk_id": chunk.id, "document_name": document.original_name, "locator": locator, "excerpt": chunk.content[:280]})
            if len(citations) == 20:
                break
        return citations

    def _scenarios(self, project: BusinessCaseProject, payload: GenerationCreate) -> list[tuple[str, dict[str, object], FinancialMetrics]]:
        result: list[tuple[str, dict[str, object], FinancialMetrics]] = []
        for name, benefit_factor, cost_factor in (("conservative", Decimal("0.8"), Decimal("1.1")), ("base", Decimal("1"), Decimal("1")), ("optimistic", Decimal("1.2"), Decimal("0.9"))):
            costs = [value * cost_factor for value in payload.financial.annual_costs]
            benefits = [value * benefit_factor for value in payload.financial.annual_benefits]
            metrics = self.financial.calculate(payload.financial.initial_investment, costs, benefits, Decimal(project.discount_rate))
            inputs: dict[str, object] = {"initial_investment": str(payload.financial.initial_investment), "annual_costs": [str(value) for value in costs], "annual_benefits": [str(value) for value in benefits], "discount_rate": str(project.discount_rate)}
            result.append((name, inputs, metrics))
        return result

    @staticmethod
    def _metrics_text(currency: str, metrics: FinancialMetrics) -> str:
        def value(item: Decimal | None, suffix: str = "") -> str:
            return f"{item}{suffix}" if item is not None else "No calculable"
        return f"ROI {value(metrics.roi_percent, '%')}; VAN {value(metrics.npv)} {currency}; TIR {value(metrics.irr_percent, '%')}; payback {value(metrics.payback_years, ' años')}"

    def _scenario_text(self, currency: str, scenarios: list[tuple[str, dict[str, object], FinancialMetrics]]) -> str:
        return "Escenarios calculados: " + "; ".join(f"{name}: {self._metrics_text(currency, metrics)}" for name, _inputs, metrics in scenarios)
