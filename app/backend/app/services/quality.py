from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import json
import re
from typing import Protocol, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import BusinessCaseVersion, ExportRecord, QualityFinding, QualityValidation, RevisionProposal, ReviewComment
from app.services.llm_provider import LLMProviderError, OpenAICompatibleClient
from app.services.review import ReviewService


RUBRIC_VERSION = "business-case-v1"
PROMPT_VERSION = "quality-critic-v2"
AGENT_DIMENSIONS = {"claridad_ejecutiva", "completitud_editorial"}
SEVERITY_SCORE_CEILINGS = {"alta": 69, "media": 84, "baja": 94}
RUBRIC_WEIGHTS = {
    "claridad_ejecutiva": 15, "evidencia_trazabilidad": 15, "alternativas_recomendacion": 10,
    "finanzas_sensibilidad": 20, "riesgos_mitigaciones": 10, "implementacion_gobernanza": 10,
    "kpis_beneficios": 10, "completitud_editorial": 10,
}


@dataclass(frozen=True)
class FindingData:
    dimension: str
    severity: str
    section_id: str | None
    explanation: str
    action: str
    deterministic: bool = True


class QualityCritic(Protocol):
    provider_model: str
    def evaluate(
        self, sections: list[dict[str, object]], deterministic_scores: dict[str, int],
        deterministic_findings: list[FindingData],
    ) -> tuple[dict[str, int], list[FindingData]]: ...


class MockQualityCritic:
    provider_model = "mock-deterministic"

    def evaluate(
        self, sections: list[dict[str, object]], deterministic_scores: dict[str, int],
        deterministic_findings: list[FindingData],
    ) -> tuple[dict[str, int], list[FindingData]]:
        return {"claridad_ejecutiva": 92, "completitud_editorial": 92}, []


class OpenAIQualityCritic:
    def __init__(self, client: OpenAICompatibleClient, model: str) -> None:
        self.client, self.model, self.provider_model = client, model, model

    def evaluate(
        self, sections: list[dict[str, object]], deterministic_scores: dict[str, int],
        deterministic_findings: list[FindingData],
    ) -> tuple[dict[str, int], list[FindingData]]:
        instructions = (
            "Evalúa exclusivamente claridad ejecutiva y completitud editorial. Devuelve sólo JSON con "
            "dimension_scores (claridad_ejecutiva y completitud_editorial, enteros 0-100) y findings. "
            "Cada finding incluye dimension, severity (alta/media/baja), section_id, explanation y action. "
            "La evaluación automática incluida en la entrada es autoritativa: no la contradigas ni repitas sus "
            "hallazgos con otras palabras. Cada hallazgo debe describir un problema observable en el texto, citar "
            "una frase o dato concreto que lo demuestre y proponer "
            "una acción distinta. No generes hallazgos genéricos, equivalentes entre sí ni sobre dimensiones fuera "
            "de las dos evaluadas. La severidad y el score deben concordar: alta=0-69, media=70-84, baja=85-94; "
            "una dimensión con 95-100 no debe tener hallazgos. No contradigas checks deterministas."
        )
        payload = {
            "sections": sections,
            "deterministic_evaluation": {
                "dimension_scores": deterministic_scores,
                "findings": [item.__dict__ for item in deterministic_findings],
            },
        }
        text = self.client.complete(self.model, instructions, json.dumps(payload, ensure_ascii=False))
        try:
            result = json.loads(text)
            scores = result["dimension_scores"]
            items = result["findings"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise LLMProviderError("The quality critic returned invalid JSON") from error
        if not isinstance(scores, dict) or not isinstance(items, list):
            raise LLMProviderError("The quality critic returned an invalid result")
        validated: dict[str, int] = {}
        for name in ("claridad_ejecutiva", "completitud_editorial"):
            value = scores.get(name)
            if not isinstance(value, int) or not 0 <= value <= 100:
                raise LLMProviderError("The quality critic returned an invalid score")
            validated[name] = value
        findings: list[FindingData] = []
        section_ids = {str(section.get("section_id")) for section in sections if section.get("section_id")}
        for item in items:
            if not isinstance(item, dict) or item.get("severity") not in {"alta", "media", "baja"}:
                raise LLMProviderError("The quality critic returned an invalid finding")
            required = ("dimension", "explanation", "action")
            if not all(isinstance(item.get(key), str) and item[key].strip() for key in required):
                raise LLMProviderError("The quality critic returned an incomplete finding")
            section_id = item.get("section_id")
            if section_id is not None and (not isinstance(section_id, str) or section_id not in section_ids):
                raise LLMProviderError("The quality critic returned an invalid section")
            dimension = str(item["dimension"])
            if dimension not in AGENT_DIMENSIONS:
                raise LLMProviderError("The quality critic returned an unsupported dimension")
            findings.append(FindingData(dimension, str(item["severity"]), section_id, str(item["explanation"]), str(item["action"]), False))
        return validated, findings


class QualityService:
    def __init__(self, session: Session, critic: QualityCritic | None = None) -> None:
        self.session = session
        self.settings = get_settings()
        if critic:
            self.critic = critic
        elif self.settings.use_mocks:
            self.critic = MockQualityCritic()
        elif self.settings.llm_provider == "openai_compatible":
            client = OpenAICompatibleClient(
                self.settings.llm_base_url, self.settings.llm_api_key_file, self.settings.llm_api_style,
                self.settings.llm_timeout_seconds, self.settings.llm_max_output_tokens, self.settings.llm_ca_bundle,
                user_agent=self.settings.llm_user_agent, originator=self.settings.llm_originator,
            )
            self.critic = OpenAIQualityCritic(client, self.settings.llm_critic_model or self.settings.llm_generator_model)
        else:
            raise RuntimeError("A quality critic must be configured server-side")

    def validate(self, version: BusinessCaseVersion) -> QualityValidation:
        previous = self.history(version.id)
        if previous and previous[0].score > 95 and previous[0].content_hash == ReviewService.content_hash(version):
            raise ValueError("La versión ya superó 95/100; edítala antes de ejecutar otra inspección.")
        content = json.loads(version.content_json)
        sections = cast(list[dict[str, object]], content.get("sections", []))
        scores, findings = self._deterministic(version, sections)
        agent_scores, agent_findings = self.critic.evaluate(sections, scores, findings)
        agent_scores = self._reconcile_agent_scores(agent_scores, agent_findings)
        for dimension, value in agent_scores.items():
            scores[dimension] = min(scores.get(dimension, 100), value)
        findings = self._deduplicate_findings([*findings, *agent_findings])
        weighted = sum(scores[name] * weight for name, weight in RUBRIC_WEIGHTS.items()) // 100
        blockers = sum(item.severity == "bloqueante" for item in findings)
        validation = QualityValidation(
            version_id=version.id, content_hash=ReviewService.content_hash(version), rubric_version=RUBRIC_VERSION,
            prompt_version=PROMPT_VERSION, provider_model=self.critic.provider_model, score=weighted,
            dimension_scores_json=json.dumps(scores, sort_keys=True),
            passed=self._passes_gate(weighted, self.settings.quality_score_threshold, findings),
        )
        validation.findings = [QualityFinding(**item.__dict__) for item in findings]
        self.session.add(validation)
        self.session.commit()
        return self.get_validation(validation.id) or validation

    def history(self, version_id: str) -> list[QualityValidation]:
        return list(self.session.scalars(select(QualityValidation).where(QualityValidation.version_id == version_id).options(selectinload(QualityValidation.findings)).order_by(QualityValidation.created_at.desc())))

    def get_validation(self, validation_id: str) -> QualityValidation | None:
        return self.session.scalar(select(QualityValidation).where(QualityValidation.id == validation_id).options(selectinload(QualityValidation.findings)))

    def get_finding(self, finding_id: str) -> QualityFinding | None:
        return self.session.get(QualityFinding, finding_id)

    def finding_to_comment(self, finding: QualityFinding, instruction: str | None) -> ReviewComment:
        if finding.comment_id:
            comment = self.session.get(ReviewComment, finding.comment_id)
            if comment:
                return comment
        validation = self.get_validation(finding.validation_id)
        if validation is None:
            raise ValueError("Validation not found")
        body = instruction.strip() if instruction and instruction.strip() else f"{finding.action} Contexto: {finding.explanation}"
        comment = ReviewComment(version_id=validation.version_id, section_id=finding.section_id, body=body)
        self.session.add(comment)
        self.session.flush()
        finding.comment_id = comment.id
        self.session.commit()
        return comment

    def finalize(self, version: BusinessCaseVersion) -> tuple[QualityValidation, datetime]:
        latest = self.history(version.id)
        if not latest:
            raise ValueError("Run quality validation before finalizing")
        validation = latest[0]
        if validation.content_hash != ReviewService.content_hash(version) or not validation.passed:
            raise ValueError("The latest quality validation does not pass the finalization gate")
        pending = self.session.scalar(select(func.count()).select_from(RevisionProposal).where(RevisionProposal.base_version_id == version.id, RevisionProposal.status == "pending")) or 0
        if pending:
            raise ValueError("Resolve pending revision proposals before finalizing")
        version.status = "final"
        version.project.status = "final"
        finalized_at = datetime.now(timezone.utc)
        self.session.commit()
        return validation, finalized_at

    def export(self, version: BusinessCaseVersion, export_format: str) -> tuple[bytes, str, str, ExportRecord]:
        if version.status != "final":
            raise ValueError("Only a final version can be exported")
        logical_hash = ReviewService.content_hash(version)
        canonical = self._canonical(version)
        if export_format == "json":
            body, media_type, extension = json.dumps(canonical, ensure_ascii=False, indent=2).encode(), "application/json", "json"
        elif export_format == "markdown":
            body, media_type, extension = self._markdown(canonical).encode(), "text/markdown; charset=utf-8", "md"
        elif export_format == "pdf":
            body, media_type, extension = self._print_html(canonical).encode(), "text/html; charset=utf-8", "html"
        else:
            raise ValueError("Unsupported export format")
        record = ExportRecord(version_id=version.id, format=export_format, content_hash=logical_hash)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return body, media_type, extension, record

    def exports(self, version_id: str) -> list[ExportRecord]:
        return list(self.session.scalars(select(ExportRecord).where(ExportRecord.version_id == version_id).order_by(ExportRecord.created_at.desc())))

    def _deterministic(self, version: BusinessCaseVersion, sections: list[dict[str, object]]) -> tuple[dict[str, int], list[FindingData]]:
        scores = {name: 100 for name in RUBRIC_WEIGHTS}
        findings: list[FindingData] = []
        by_id = {str(item.get("section_id")): item for item in sections}
        required = {"executive_summary", "alternatives", "recommendation", "financial_analysis", "sensitivity", "risks", "implementation_plan", "kpis", "sources_annexes"}
        missing = sorted(required - set(by_id))
        if missing:
            scores["completitud_editorial"] = 0
            findings.append(FindingData("completitud_editorial", "bloqueante", None, f"Faltan secciones obligatorias: {', '.join(missing)}.", "Completar todas las secciones obligatorias."))
        if not version.citations:
            scores["evidencia_trazabilidad"] = 0
            findings.append(FindingData("evidencia_trazabilidad", "bloqueante", "sources_annexes", "La versión no contiene fuentes ni citas verificables.", "Adjuntar evidencia e incluir citas antes de finalizar."))
        elif any(not cast(list[object], item.get("citation_ids", [])) for item in sections if item.get("section_id") not in {"cover"}):
            scores["evidencia_trazabilidad"] = 70
            findings.append(FindingData("evidencia_trazabilidad", "alta", None, "Existen secciones sin una referencia trazable.", "Añadir citas a las afirmaciones materiales."))
        alternatives = str(by_id.get("alternatives", {}).get("content", ""))
        if not all(marker in alternatives for marker in ("A", "B", "C")):
            scores["alternativas_recomendacion"] = 40
            findings.append(FindingData("alternativas_recomendacion", "alta", "alternatives", "No se distinguen tres alternativas comparables.", "Incluir no hacer nada, solución parcial y recomendada."))
        if len(version.scenarios) < 3:
            scores["finanzas_sensibilidad"] = 0
            findings.append(FindingData("finanzas_sensibilidad", "bloqueante", "financial_analysis", "Faltan escenarios financieros deterministas.", "Recalcular escenarios conservador, base y optimista."))
        for dimension, section_id, label in (
            ("riesgos_mitigaciones", "risks", "riesgos y mitigaciones"),
            ("implementacion_gobernanza", "implementation_plan", "plan y gobernanza"),
            ("kpis_beneficios", "kpis", "KPIs y beneficios"),
        ):
            if len(str(by_id.get(section_id, {}).get("content", "")).strip()) < 40:
                scores[dimension] = 50
                findings.append(FindingData(dimension, "media", section_id, f"El contenido de {label} es insuficiente.", f"Ampliar {label} con responsables y datos verificables."))
        if any("Dato requerido" in cast(list[str], item.get("labels", [])) for item in sections):
            scores["completitud_editorial"] = min(scores["completitud_editorial"], 65)
            findings.append(FindingData("completitud_editorial", "alta", None, "Persisten datos requeridos sin confirmar.", "Resolver o justificar los datos pendientes."))
        return scores, findings

    @staticmethod
    def _reconcile_agent_scores(scores: dict[str, int], findings: list[FindingData]) -> dict[str, int]:
        """Keep the critic's numeric verdict consistent with the severity of its findings."""
        reconciled = dict(scores)
        for finding in findings:
            ceiling = SEVERITY_SCORE_CEILINGS.get(finding.severity)
            if finding.dimension in AGENT_DIMENSIONS and ceiling is not None:
                reconciled[finding.dimension] = min(reconciled.get(finding.dimension, 100), ceiling)
        return reconciled

    @classmethod
    def _deduplicate_findings(cls, findings: list[FindingData]) -> list[FindingData]:
        """Collapse materially equivalent findings, preferring deterministic evidence."""
        unique: list[FindingData] = []
        severity_order = {"bloqueante": 0, "alta": 1, "media": 2, "baja": 3}
        for candidate in sorted(
            findings,
            key=lambda item: (not item.deterministic, severity_order.get(item.severity, 4)),
        ):
            if any(cls._findings_are_similar(candidate, current) for current in unique):
                continue
            unique.append(candidate)
        return unique

    @staticmethod
    def _passes_gate(score: int, threshold: int, findings: list[FindingData]) -> bool:
        """A high score cannot approve a document with blocking or high-severity findings."""
        unresolved_critical = any(item.severity in {"bloqueante", "alta"} for item in findings)
        return score >= threshold and not unresolved_critical

    @staticmethod
    def _findings_are_similar(left: FindingData, right: FindingData) -> bool:
        if left.dimension != right.dimension:
            return False
        if left.section_id and right.section_id and left.section_id != right.section_id:
            return False
        stopwords = {
            "para", "como", "esta", "este", "esto", "entre", "desde", "hasta", "sobre", "cada", "debe",
            "deben", "tiene", "tener", "hacer", "falta", "faltan", "incluye", "incluir", "seccion", "contenido",
            "datos", "informacion", "hallazgo", "version", "agregar", "anadir", "completar", "ampliar",
        }

        def tokens(item: FindingData) -> set[str]:
            words = re.findall(r"[a-záéíóúñ]{4,}", f"{item.explanation} {item.action}".casefold())
            return {word for word in words if word not in stopwords}

        left_tokens, right_tokens = tokens(left), tokens(right)
        if not left_tokens or not right_tokens:
            return False
        overlap = len(left_tokens & right_tokens)
        return overlap >= 3 and overlap / min(len(left_tokens), len(right_tokens)) >= 0.6

    @staticmethod
    def _canonical(version: BusinessCaseVersion) -> dict[str, object]:
        content = json.loads(version.content_json)
        inputs = json.loads(version.input_snapshot_json)
        document_kind = inputs.get("document_kind", "business_case")
        return {
            "version_id": version.id, "version_number": version.version_number, "status": version.status,
            "document_kind": document_kind,
            "created_at": version.created_at.isoformat(), "project": {"name": version.project.name, "organization": version.project.organization, "currency": version.project.currency},
            "table_of_contents": content["table_of_contents"], "sections": content["sections"],
            "citations": [{"id": item.id, "document_name": item.document_name, "locator": item.locator, "excerpt": item.excerpt} for item in version.citations],
            "assumptions": [{"section_id": item.section_id, "text": item.text, "impact": item.impact, "status": item.status} for item in version.assumptions],
            "disclaimer": "Este documento apoya el análisis y requiere validación de los responsables; no garantiza una decisión financiera.",
        }

    @staticmethod
    def _markdown(document: dict[str, object]) -> str:
        project = cast(dict[str, object], document["project"])
        lines = [f"# {project['name']}", "", f"**Organización:** {project['organization']}  ", f"**Versión:** {document['version_number']}  ", f"**Fecha:** {document['created_at']}", "", "## Índice", ""]
        for item in cast(list[dict[str, object]], document["table_of_contents"]):
            lines.append(f"{item['ordinal']}. {item['title']}")
        for section in cast(list[dict[str, object]], document["sections"]):
            lines.extend(["", f"## {section['title']}", "", str(section["content"])])
        lines.extend(["", "## Fuentes y citas", ""])
        for citation in cast(list[dict[str, object]], document["citations"]):
            lines.append(f"- **{citation['document_name']}**, {citation['locator']}: {citation['excerpt']}")
        assumptions = cast(list[dict[str, object]], document["assumptions"])
        if assumptions:
            lines.extend(["", "## Supuestos pendientes", ""] + [f"- {item['text']} — {item['impact']}" for item in assumptions])
        lines.extend(["", "---", str(document["disclaimer"])])
        return "\n".join(lines) + "\n"

    @staticmethod
    def _print_html(document: dict[str, object]) -> str:
        project = cast(dict[str, object], document["project"])
        is_blueprint = document.get("document_kind") == "blueprint"
        document_label = "Blueprint" if is_blueprint else "Business Case"
        brand_label = "mabe" if is_blueprint else "Casecraft"
        section_items = cast(list[dict[str, object]], document["sections"])
        toc = "".join(
            f'<li><a href="#section-{index}"><span>{index:02d}</span>{escape(str(item["title"]))}</a></li>'
            for index, item in enumerate(section_items, start=1)
        )
        sections = "".join(
            f'<section id="section-{index}" class="document-section">'
            f'<div class="section-number">{index:02d}</div><div class="section-body">'
            f'<p class="section-kicker">SECCIÓN {index:02d}</p><h2>{escape(str(item["title"]))}</h2>'
            f'{QualityService._section_labels(cast(list[object], item.get("labels", [])))}'
            f'<div class="section-content">{QualityService._render_markdown(str(item["content"]))}</div></div></section>'
            for index, item in enumerate(section_items, start=1)
        )
        citations = "".join(
            f'<li><div class="citation-index">{index:02d}</div><div><strong>{escape(str(item["document_name"]))}</strong>'
            f'<span>{escape(str(item["locator"]))}</span><p>{escape(str(item["excerpt"]))}</p></div></li>'
            for index, item in enumerate(cast(list[dict[str, object]], document["citations"]), start=1)
        )
        assumptions = cast(list[dict[str, object]], document["assumptions"])
        assumption_items = "".join(
            f'<li><strong>{escape(str(item["text"]))}</strong><span>{escape(str(item["impact"]))}</span></li>'
            for item in assumptions
        )
        assumption_notice = (
            f'<aside class="assumption-notice"><div><span>{len(assumptions):02d}</span></div><div><strong>Supuestos pendientes de validación</strong>'
            f'<p>Estos elementos deben confirmarse con los responsables antes de ejecutar la recomendación.</p><ul>{assumption_items}</ul></div></aside>'
            if assumptions else ""
        )
        styles = """
@page{size:A4;margin:18mm 16mm 20mm;@bottom-left{content:'CASECRAFT · BUSINESS CASE';color:#806f84;font:7.5pt Arial,sans-serif;letter-spacing:.08em}@bottom-right{content:'Página ' counter(page) ' de ' counter(pages);color:#806f84;font:8pt Arial,sans-serif}}
@page:first{margin:0;@bottom-left{content:''}@bottom-right{content:''}}
*{box-sizing:border-box}
html{background:#eee7f0}
body{max-width:210mm;margin:0 auto;background:#fff;color:#2d1732;font:10.5pt Arial,Helvetica,sans-serif;line-height:1.62;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.cover{position:relative;display:flex;min-height:297mm;overflow:hidden;padding:28mm 24mm;flex-direction:column;background:linear-gradient(125deg,#922b70 0%,#621f65 52%,#35164d 100%);color:#fff;break-after:page}
.cover:after{content:'';position:absolute;inset:-25% -42% -30% 30%;opacity:.22;background:repeating-radial-gradient(ellipse at 100% 50%,transparent 0 24px,rgba(255,255,255,.34) 25px 26px,transparent 27px 50px);transform:rotate(-10deg)}
.cover>*{position:relative;z-index:1}
.cover-brand{display:flex;align-items:center;gap:12px;font-size:12pt;font-weight:700;letter-spacing:.02em}
.cover-brand:after{content:'';width:46mm;height:1px;background:linear-gradient(90deg,rgba(255,255,255,.7),transparent)}
.cover-copy{margin:auto 0}
.cover-eyebrow{margin:0 0 7mm;color:#f3cbe7;font-size:8pt;font-weight:700;letter-spacing:.22em;text-transform:uppercase}
.cover h1{max-width:155mm;margin:0;font-size:32pt;line-height:1.08;letter-spacing:-.035em}
.cover-subtitle{max-width:125mm;margin:7mm 0 0;color:#eadbea;font-size:13pt;line-height:1.5}
.cover-meta{display:grid;grid-template-columns:1.3fr .7fr .9fr;gap:4mm;padding-top:7mm;border-top:1px solid rgba(255,255,255,.28)}
.cover-meta span{display:block;margin-bottom:1.5mm;color:#ddbad8;font-size:7pt;letter-spacing:.14em;text-transform:uppercase}
.cover-meta strong{font-size:9.5pt;font-weight:600}
.contents{min-height:245mm;padding-top:5mm;break-after:page}
.document-eyebrow,.section-kicker{margin:0 0 2mm;color:#9a2f78;font-size:7.5pt;font-weight:700;letter-spacing:.18em;text-transform:uppercase}
.contents h2,.annex h2{margin:0 0 4mm;color:#371a40;font-size:23pt;letter-spacing:-.025em}
.contents-intro{max-width:130mm;margin:0 0 10mm;color:#756278}
.toc{display:grid;grid-template-columns:1fr 1fr;gap:0 9mm;margin:0;padding:0;list-style:none}
.toc li{border-bottom:1px solid #eadfeb;break-inside:avoid}
.toc a{display:grid;grid-template-columns:9mm 1fr;gap:3mm;align-items:center;padding:3.2mm 0;color:#432147;text-decoration:none}
.toc span{color:#a43a82;font:7.5pt 'Courier New',monospace}
.document-section{display:grid;grid-template-columns:12mm minmax(0,1fr);gap:5mm;margin:0 0 10mm;padding-top:2mm;break-inside:auto}
.section-number{display:grid;place-items:center;width:10mm;height:10mm;border-radius:50%;background:#f4e7f1;color:#8e276f;font:700 7.5pt 'Courier New',monospace}
.section-body{min-width:0}
.document-section>.section-body>h2{margin:0 0 4mm;color:#3a1c41;font-size:17pt;line-height:1.2;letter-spacing:-.018em;break-after:avoid}
.section-content{color:#4b3a4f;line-height:1.68;orphans:3;widows:3}
.section-content p{margin:0 0 3.6mm;text-align:left}
.section-content h1,.section-content h2,.section-content h3,.section-content h4{margin:6mm 0 2.5mm;color:#432147;line-height:1.28;break-after:avoid}
.section-content h1{font-size:14pt}.section-content h2{font-size:12.5pt}.section-content h3{padding-bottom:1.5mm;border-bottom:1px solid #eadfeb;font-size:11pt}.section-content h4{font-size:10.5pt}
.section-content strong{color:#35163e;font-weight:700}.section-content em{color:#665069}
.section-content ul,.section-content ol{margin:1mm 0 4mm;padding-left:6mm}.section-content li{margin:0 0 2mm;padding-left:1.5mm;break-inside:avoid}.section-content li::marker{color:#9a2f78;font-weight:700}
.section-content blockquote{margin:4mm 0;padding:3mm 4mm;border-left:1.2mm solid #a43a82;background:#faf3f8;color:#604c63;break-inside:avoid}.section-content blockquote p{margin:0}
.section-content code{padding:.4mm 1mm;border-radius:1mm;background:#f4edf4;color:#70245d;font:8.5pt 'Courier New',monospace}
.section-content pre{margin:4mm 0;padding:4mm;overflow-wrap:anywhere;border-radius:2mm;background:#351a3d;color:#f9eff7;white-space:pre-wrap;break-inside:avoid}.section-content pre code{padding:0;background:transparent;color:inherit}
.section-content table{width:100%;max-width:100%;margin:4mm 0 5mm;border-collapse:collapse;table-layout:fixed;font-size:8.5pt}.section-content thead{display:table-header-group}.section-content tr{break-inside:avoid;page-break-inside:avoid}.section-content th,.section-content td{min-width:0;padding:2.2mm;border:1px solid #e4d8e5;overflow-wrap:anywhere;word-break:normal;text-align:left;vertical-align:top}.section-content th{background:#f6edf4;color:#512049;font-weight:700}.section-content tr:nth-child(even) td{background:#fdfafd}
.section-content table:has(th:nth-child(6)){font-size:7.4pt;line-height:1.48}.section-content table:has(th:nth-child(6)) th,.section-content table:has(th:nth-child(6)) td{padding:1.6mm}
.section-content hr{margin:6mm 0;border:0;border-top:1px solid #dfd2e1}
.source-reference{display:inline;padding:.35mm 1.3mm;border-radius:1.5mm;background:#f3edf4;color:#78657b;font-size:7.5pt;font-weight:600;line-height:1.5;white-space:normal;overflow-wrap:anywhere;word-break:break-word;box-decoration-break:clone;-webkit-box-decoration-break:clone}
.labels{display:flex;gap:2mm;margin:-1mm 0 4mm;flex-wrap:wrap}
.label{padding:1mm 2.5mm;border:1px solid #dbc5da;border-radius:99px;background:#faf3f8;color:#7a2868;font-size:7.5pt;font-weight:700}
.assumption-notice{display:grid;grid-template-columns:13mm 1fr;gap:5mm;margin:0 0 10mm;padding:5mm;border:1px solid #e4b84a;border-radius:3mm;background:#fff9e8;break-inside:avoid}
.assumption-notice>div:first-child span{display:grid;place-items:center;width:11mm;height:11mm;border-radius:50%;background:#9b6800;color:#fff;font-weight:700}
.assumption-notice strong{color:#694900}
.assumption-notice p{margin:1mm 0 3mm;color:#765f2e}
.assumption-notice ul{margin:0;padding-left:5mm}.assumption-notice li{margin-top:2mm}.assumption-notice li span{display:block;color:#765f2e;font-size:9pt}
.annex{padding-top:4mm;break-before:page}
.citation-list{display:grid;gap:3mm;margin:7mm 0 0;padding:0;list-style:none}
.citation-list li{display:grid;grid-template-columns:10mm 1fr;gap:4mm;padding:4mm;border:1px solid #e8dce9;border-radius:3mm;background:#fdfbfd;break-inside:avoid}
.citation-index{color:#a43a82;font:7.5pt 'Courier New',monospace}
.citation-list strong,.citation-list span{display:block}.citation-list span{margin-top:1mm;color:#806f84;font-size:8pt}.citation-list p{margin:2mm 0 0;color:#58465c;font-size:9pt;line-height:1.5}
.document-footer{margin-top:12mm;padding:5mm 0 0;border-top:1px solid #dfd2e1;color:#806f84;font-size:8pt;line-height:1.5}
@media screen{body{box-shadow:0 20px 70px rgba(45,23,50,.18)}.cover,.contents,main{padding-left:16mm;padding-right:16mm}.cover{padding-left:24mm;padding-right:24mm}.contents,main{padding-top:18mm;padding-bottom:18mm}}
@media print{html{background:#fff}body{max-width:none}.contents,main{padding:0}.cover{padding:28mm 24mm}}
"""
        styles = styles.replace("CASECRAFT · BUSINESS CASE", f"{brand_label.upper()} · {document_label.upper()}")
        project_name = escape(str(project["name"]))
        organization = escape(str(project["organization"]))
        created_at = escape(str(document["created_at"])[:10])
        return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{project_name} · {document_label}</title><style>{styles}</style></head>
<body><header class="cover"><div class="cover-brand">{brand_label}</div><div class="cover-copy"><p class="cover-eyebrow">{document_label} profesional</p><h1>{project_name}</h1><p class="cover-subtitle">Documento ejecutivo para evaluación, alineación y toma de decisiones.</p></div><div class="cover-meta"><div><span>Organización</span><strong>{organization}</strong></div><div><span>Versión</span><strong>{document['version_number']}</strong></div><div><span>Fecha</span><strong>{created_at}</strong></div></div></header>
<nav class="contents" aria-label="Índice"><p class="document-eyebrow">Estructura del documento</p><h2>Contenido</h2><p class="contents-intro">Una lectura estructurada del contexto, la recomendación, su viabilidad y las condiciones necesarias para ejecutar la decisión.</p><ol class="toc">{toc}</ol></nav>
<main>{assumption_notice}{sections}<section class="annex"><p class="document-eyebrow">Anexo de evidencia</p><h2>Fuentes y citas</h2><p class="contents-intro">Referencias conservadas para respaldar la trazabilidad de las afirmaciones y facilitar su validación.</p><ol class="citation-list">{citations}</ol></section><footer class="document-footer"><strong>Aviso de uso.</strong> {escape(str(document['disclaimer']))}<br>Versión {document['version_number']} · Identificador {escape(str(document['version_id']))}</footer></main>
<script>window.addEventListener('load',()=>window.print())</script></body></html>"""

    @staticmethod
    def _section_labels(labels: list[object]) -> str:
        if not labels:
            return ""
        items = "".join(f'<span class="label">{escape(str(label))}</span>' for label in labels)
        return f'<div class="labels">{items}</div>'

    @staticmethod
    def _render_markdown(markdown: str) -> str:
        """Render the small, safe Markdown subset used by generated sections."""
        lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        output: list[str] = []
        index = 0
        paragraph: list[str] = []

        def flush_paragraph() -> None:
            if paragraph:
                text = " ".join(part.strip() for part in paragraph if part.strip())
                if text:
                    output.append(f"<p>{QualityService._render_inline_markdown(text)}</p>")
                paragraph.clear()

        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            if not stripped:
                flush_paragraph()
                index += 1
                continue

            if stripped.startswith("```"):
                flush_paragraph()
                language = stripped[3:].strip()
                code: list[str] = []
                index += 1
                while index < len(lines) and not lines[index].strip().startswith("```"):
                    code.append(lines[index])
                    index += 1
                if index < len(lines):
                    index += 1
                language_attr = f' data-language="{escape(language)}"' if language else ""
                output.append(f"<pre{language_attr}><code>{escape(chr(10).join(code))}</code></pre>")
                continue

            heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*$", stripped)
            if heading:
                flush_paragraph()
                level = min(len(heading.group(1)), 4)
                output.append(f"<h{level}>{QualityService._render_inline_markdown(heading.group(2))}</h{level}>")
                index += 1
                continue

            if stripped in {"---", "***", "___"}:
                flush_paragraph()
                output.append("<hr>")
                index += 1
                continue

            if index + 1 < len(lines) and "|" in stripped and re.match(r"^\s*\|?\s*:?-{3,}", lines[index + 1]):
                flush_paragraph()
                headers = QualityService._markdown_cells(stripped)
                index += 2
                rows: list[list[str]] = []
                while index < len(lines) and "|" in lines[index] and lines[index].strip():
                    rows.append(QualityService._markdown_cells(lines[index]))
                    index += 1
                head = "".join(f"<th>{QualityService._render_inline_markdown(cell)}</th>" for cell in headers)
                body = "".join("<tr>" + "".join(f"<td>{QualityService._render_inline_markdown(cell)}</td>" for cell in row) + "</tr>" for row in rows)
                output.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
                continue

            list_match = re.match(r"^\s*([-+*]|\d+[.)])\s+(.+)$", line)
            if list_match:
                flush_paragraph()
                ordered = list_match.group(1)[0].isdigit()
                tag = "ol" if ordered else "ul"
                items: list[str] = []
                while index < len(lines):
                    item = re.match(r"^\s*([-+*]|\d+[.)])\s+(.+)$", lines[index])
                    if not item or item.group(1)[0].isdigit() != ordered:
                        break
                    items.append(f"<li>{QualityService._render_inline_markdown(item.group(2).strip())}</li>")
                    index += 1
                output.append(f"<{tag}>{''.join(items)}</{tag}>")
                continue

            if stripped.startswith(">"):
                flush_paragraph()
                quote: list[str] = []
                while index < len(lines) and lines[index].strip().startswith(">"):
                    quote.append(lines[index].strip()[1:].strip())
                    index += 1
                output.append(f"<blockquote><p>{QualityService._render_inline_markdown(' '.join(quote))}</p></blockquote>")
                continue

            paragraph.append(stripped)
            index += 1

        flush_paragraph()
        return "".join(output)

    @staticmethod
    def _markdown_cells(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    @staticmethod
    def _render_inline_markdown(text: str) -> str:
        code_tokens: list[str] = []
        reference_tokens: list[str] = []

        def code_token(match: re.Match[str]) -> str:
            code_tokens.append(f"<code>{escape(match.group(1))}</code>")
            return f"\x00CODE{len(code_tokens) - 1}\x00"

        def reference_token(match: re.Match[str]) -> str:
            label = re.sub(r"\s+", " ", match.group(1)).strip()
            reference_tokens.append(f'<span class="source-reference">Fuente: {escape(label)}</span>')
            return f"\x00REF{len(reference_tokens) - 1}\x00"

        protected = re.sub(r"`([^`]+)`", code_token, text)
        protected = re.sub(r"\[([^\]]*\.md\b[^\]]*)\]", reference_token, protected, flags=re.IGNORECASE)
        rendered = escape(protected)
        rendered = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rendered)
        rendered = re.sub(r"__(.+?)__", r"<strong>\1</strong>", rendered)
        rendered = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", rendered)
        rendered = re.sub(r"(?<!_)_([^_]+?)_(?!_)", r"<em>\1</em>", rendered)
        for token_index, value in enumerate(code_tokens):
            rendered = rendered.replace(f"\x00CODE{token_index}\x00", value)
        for token_index, value in enumerate(reference_tokens):
            rendered = rendered.replace(f"\x00REF{token_index}\x00", value)
        return rendered
