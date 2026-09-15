from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Protocol, cast
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import Assumption, BusinessCaseVersion, CitationSnapshot, FinancialScenario, QualityReport, ReviewComment, RevisionProposal, VersionChange
from app.schemas import ManualRevisionCreate, PatchOperation, ReviewCommentCreate
from app.services.llm_provider import LLMProviderError, OpenAICompatibleClient


class ProposalProvider(Protocol):
    def propose(self, comment: ReviewComment, section: dict[str, object]) -> tuple[str, str]: ...


class MockProposalProvider:
    def propose(self, comment: ReviewComment, section: dict[str, object]) -> tuple[str, str]:
        current = str(section["content"])
        adjusted = f"{current}\n\nAjuste propuesto: {comment.body}"
        return "Se incorpora la instrucción del revisor sin alterar citas ni métricas protegidas.", adjusted


class OpenAIProposalProvider:
    def __init__(self, client: OpenAICompatibleClient, model: str) -> None:
        self.client = client
        self.model = model

    def propose(self, comment: ReviewComment, section: dict[str, object]) -> tuple[str, str]:
        instructions = (
            "Reescribe la sección como consultor senior a partir del texto actual y la retroalimentación. Integra el cambio dentro de una narrativa coherente, más clara, descriptiva y útil para una decisión ejecutiva; no anexes simplemente la instrucción ni copies mecánicamente las palabras del usuario. "
            "No inventes hechos, elimines citas ni cambies métricas calculadas. Marca como supuesto o dato requerido aquello que no esté sustentado. "
            "Devuelve sólo JSON con rationale y after; ambos deben ser strings."
        )
        payload = {"review_instruction": comment.body, "section_id": section["section_id"], "current_text": section["content"]}
        text = self.client.complete(self.model, instructions, json.dumps(payload, ensure_ascii=False))
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise LLMProviderError("The revision provider returned invalid JSON") from error
        if not isinstance(parsed, dict) or not isinstance(parsed.get("rationale"), str) or not isinstance(parsed.get("after"), str):
            raise LLMProviderError("The revision provider returned an invalid proposal")
        if not parsed["rationale"].strip() or not parsed["after"].strip():
            raise LLMProviderError("The revision provider returned an empty proposal")
        return cast(str, parsed["rationale"]).strip(), cast(str, parsed["after"]).strip()


class ReviewService:
    def __init__(self, session: Session, provider: ProposalProvider | None = None) -> None:
        self.session = session
        settings = get_settings()
        if provider is not None:
            self.provider = provider
        elif settings.use_mocks:
            self.provider = MockProposalProvider()
        elif settings.llm_provider == "openai_compatible":
            client = OpenAICompatibleClient(
                settings.llm_base_url,
                settings.llm_api_key_file,
                settings.llm_api_style,
                settings.llm_timeout_seconds,
                settings.llm_max_output_tokens,
                settings.llm_ca_bundle,
                user_agent=settings.llm_user_agent,
                originator=settings.llm_originator,
            )
            self.provider = OpenAIProposalProvider(client, settings.llm_generator_model)
        else:
            raise RuntimeError("A revision proposal provider must be configured server-side")

    @staticmethod
    def content_hash(version: BusinessCaseVersion) -> str:
        return hashlib.sha256(version.content_json.encode("utf-8")).hexdigest()

    def get_version(self, version_id: str) -> BusinessCaseVersion | None:
        return self.session.scalar(
            select(BusinessCaseVersion).where(BusinessCaseVersion.id == version_id).options(
                selectinload(BusinessCaseVersion.scenarios), selectinload(BusinessCaseVersion.quality_report),
                selectinload(BusinessCaseVersion.citations), selectinload(BusinessCaseVersion.assumptions),
            )
        )

    def create_comment(self, version: BusinessCaseVersion, payload: ReviewCommentCreate) -> ReviewComment:
        if payload.section_id and payload.section_id not in self._section_map(version):
            raise ValueError("Section not found in base version")
        comment = ReviewComment(version_id=version.id, section_id=payload.section_id, block_id=payload.block_id, body=payload.body)
        self.session.add(comment)
        self.session.commit()
        self.session.refresh(comment)
        return comment

    def list_comments(self, version_id: str, status: str | None = None) -> list[ReviewComment]:
        statement = select(ReviewComment).where(ReviewComment.version_id == version_id)
        if status:
            statement = statement.where(ReviewComment.status == status)
        return list(self.session.scalars(statement.order_by(ReviewComment.created_at.desc())))

    def get_comment(self, comment_id: str) -> ReviewComment | None:
        return self.session.get(ReviewComment, comment_id)

    def create_proposal(self, comment: ReviewComment) -> RevisionProposal:
        if comment.status != "open":
            raise ValueError("Only open comments can produce proposals")
        version = self.get_version(comment.version_id)
        if version is None:
            raise ValueError("Base version not found")
        sections = self._section_map(version)
        if not comment.section_id:
            raise ValueError("Agent proposals require a section comment")
        section = sections.get(comment.section_id)
        if section is None:
            raise ValueError("Section not found in base version")
        rationale, after = self.provider.propose(comment, section)
        operation = PatchOperation(operation="replace_text", section_id=comment.section_id, before=str(section["content"]), after=after)
        impact = self._impact([operation])
        proposal = RevisionProposal(
            comment_id=comment.id, base_version_id=version.id, base_content_hash=self.content_hash(version), status="pending",
            rationale=rationale, patch_json=json.dumps([operation.model_dump()], ensure_ascii=False), impact_json=json.dumps(impact, ensure_ascii=False),
        )
        self.session.add(proposal)
        self.session.commit()
        self.session.refresh(proposal)
        return proposal

    def get_proposal(self, proposal_id: str) -> RevisionProposal | None:
        return self.session.get(RevisionProposal, proposal_id)

    def accept(self, proposal: RevisionProposal) -> BusinessCaseVersion:
        if proposal.status != "pending":
            raise ValueError("Only pending proposals can be accepted")
        base = self.get_version(proposal.base_version_id)
        if base is None:
            raise ValueError("Base version not found")
        if self._latest_version_id(base.project_id) != base.id or self.content_hash(base) != proposal.base_content_hash:
            proposal.status = "obsolete"
            proposal.resolved_at = datetime.now(timezone.utc)
            self.session.commit()
            raise ValueError("Proposal is obsolete because the base version changed")
        content = json.loads(base.content_json)
        sections = {section["section_id"]: section for section in content["sections"]}
        operations = [PatchOperation.model_validate(item) for item in json.loads(proposal.patch_json)]
        changed: list[str] = []
        for operation in operations:
            if operation.operation != "replace_text" or operation.before is None or operation.after is None:
                raise ValueError("Unsupported patch operation")
            section = sections.get(operation.section_id)
            if section is None or section["content"] != operation.before:
                raise ValueError("Patch no longer matches the base content")
            section["content"] = operation.after
            changed.append(operation.section_id)
        version = self._clone_version(base, content, "agent", proposal.rationale, changed)
        proposal.status = "accepted"
        proposal.applied_version_id = version.id
        proposal.resolved_at = datetime.now(timezone.utc)
        comment = self.get_comment(proposal.comment_id)
        if comment:
            comment.status = "resolved"
            comment.resolved_at = proposal.resolved_at
        self.session.commit()
        return version

    def reject(self, proposal: RevisionProposal) -> RevisionProposal:
        if proposal.status != "pending":
            raise ValueError("Only pending proposals can be rejected")
        proposal.status = "rejected"
        proposal.resolved_at = datetime.now(timezone.utc)
        comment = self.get_comment(proposal.comment_id)
        if comment:
            comment.status = "rejected"
            comment.resolved_at = proposal.resolved_at
        self.session.commit()
        return proposal

    def manual_revision(self, base: BusinessCaseVersion, payload: ManualRevisionCreate) -> BusinessCaseVersion:
        if self._latest_version_id(base.project_id) != base.id or self.content_hash(base) != payload.base_content_hash:
            raise ValueError("Base version changed; reload before saving")
        content = json.loads(base.content_json)
        sections = {section["section_id"]: section for section in content["sections"]}
        changed: list[str] = []
        for edit in payload.edits:
            section = sections.get(edit.section_id)
            if section is None:
                raise ValueError(f"Section not found: {edit.section_id}")
            if section["content"] != edit.content:
                section["content"] = edit.content
                changed.append(edit.section_id)
        if not changed:
            raise ValueError("Revision contains no changes")
        version = self._clone_version(base, content, "manual", payload.reason, changed)
        self.session.commit()
        return version

    def restore(self, historical: BusinessCaseVersion, reason: str) -> BusinessCaseVersion:
        latest_id = self._latest_version_id(historical.project_id)
        if latest_id is None:
            raise ValueError("Project has no versions")
        version = self._clone_version(historical, json.loads(historical.content_json), "restore", reason, ["all"])
        version.change.base_version_id = latest_id if version.change else None
        self.session.commit()
        return version

    def comparison(self, first: BusinessCaseVersion, second: BusinessCaseVersion) -> list[dict[str, object]]:
        if first.project_id != second.project_id:
            raise ValueError("Versions belong to different projects")
        before = self._section_map(first)
        after = self._section_map(second)
        return [
            {"section_id": section_id, "before": before.get(section_id, {}).get("content"), "after": after.get(section_id, {}).get("content")}
            for section_id in sorted(set(before) | set(after))
            if before.get(section_id, {}).get("content") != after.get(section_id, {}).get("content")
        ]

    def history(self, project_id: str) -> list[VersionChange]:
        return list(self.session.scalars(select(VersionChange).join(BusinessCaseVersion).where(BusinessCaseVersion.project_id == project_id).order_by(VersionChange.created_at.desc())))

    def _clone_version(self, base: BusinessCaseVersion, content: dict[str, object], source: str, reason: str, changed: list[str]) -> BusinessCaseVersion:
        number = cast(int, self.session.scalar(select(func.max(BusinessCaseVersion.version_number)).where(BusinessCaseVersion.project_id == base.project_id)) or 0) + 1
        citation_ids = {item.id: str(uuid4()) for item in base.citations}
        for section in cast(list[dict[str, object]], content["sections"]):
            section["citation_ids"] = [citation_ids.get(str(item), str(item)) for item in cast(list[object], section.get("citation_ids", []))]
        version = BusinessCaseVersion(
            project_id=base.project_id, version_number=number, status="ready", content_json=json.dumps(content, ensure_ascii=False),
            input_snapshot_json=base.input_snapshot_json, rules_snapshot_json=base.rules_snapshot_json,
        )
        version.scenarios = [FinancialScenario(name=item.name, inputs_json=item.inputs_json, metrics_json=item.metrics_json) for item in base.scenarios]
        if base.quality_report:
            version.quality_report = QualityReport(score=base.quality_report.score, findings_json=base.quality_report.findings_json, compliance_json=base.quality_report.compliance_json)
        version.citations = [CitationSnapshot(id=citation_ids[item.id], document_id=item.document_id, chunk_id=item.chunk_id, document_name=item.document_name, locator=item.locator, excerpt=item.excerpt) for item in base.citations]
        version.assumptions = [Assumption(section_id=item.section_id, text=item.text, impact=item.impact, status=item.status) for item in base.assumptions]
        version.change = VersionChange(base_version_id=base.id, source=source, reason=reason, changed_blocks_json=json.dumps(changed))
        base.project.status = "in_review"
        self.session.add(version)
        self.session.flush()
        return version

    def _latest_version_id(self, project_id: str) -> str | None:
        return self.session.scalar(select(BusinessCaseVersion.id).where(BusinessCaseVersion.project_id == project_id).order_by(BusinessCaseVersion.version_number.desc()).limit(1))

    @staticmethod
    def _section_map(version: BusinessCaseVersion) -> dict[str, dict[str, object]]:
        content = json.loads(version.content_json)
        return {str(section["section_id"]): section for section in content["sections"]}

    @staticmethod
    def _impact(operations: list[PatchOperation]) -> dict[str, object]:
        sections = [operation.section_id for operation in operations]
        financial = "financial_analysis" in sections or any(operation.operation == "request_financial_recalculation" for operation in operations)
        return {"affected_sections": sections, "financial_recalculation": financial, "citations_preserved": True, "human_approval_required": True}
