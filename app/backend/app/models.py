from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    GENERATED = "generated"
    IN_REVIEW = "in_review"
    FINAL = "final"


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"
    REQUIRES_OCR = "requires_ocr"


class RuleStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class GenerationStatus(StrEnum):
    PREPARING = "preparing"
    WRITING = "writing"
    CALCULATING = "calculating"
    VALIDATING = "validating"
    READY = "ready"
    ERROR = "error"


class BusinessCaseProject(Base):
    __tablename__ = "business_case_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    organization: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3))
    horizon_years: Mapped[int] = mapped_column(Integer)
    discount_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    setup_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default=ProjectStatus.DRAFT.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    documents: Mapped[list["SourceDocument"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    versions: Mapped[list["BusinessCaseVersion"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    generation_runs: Mapped[list["GenerationRun"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    interview: Mapped["AgentInterview | None"] = relationship(back_populates="project", cascade="all, delete-orphan", uselist=False)


class AgentInterview(Base):
    __tablename__ = "agent_interviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("business_case_projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="collecting")
    readiness_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    strengths_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    gaps_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    questions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    answers_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    analysis_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    project: Mapped[BusinessCaseProject] = relationship(back_populates="interview")


class SourceDocument(Base):
    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint("project_id", "sha256", name="uq_documents_project_sha256"),
        Index("ix_documents_project_updated", "project_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("business_case_projects.id", ondelete="CASCADE"), nullable=False)
    original_name: Mapped[str] = mapped_column(String(180), nullable=False)
    storage_name: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=DocumentStatus.PENDING.value)
    error_code: Mapped[str | None] = mapped_column(String(64))
    included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[BusinessCaseProject] = relationship(back_populates="documents")
    chunks: Mapped[list["EvidenceChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="EvidenceChunk.ordinal"
    )


class EvidenceChunk(Base):
    __tablename__ = "evidence_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_chunks_document_ordinal"),
        Index("ix_chunks_document_included", "document_id", "included"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    sheet_name: Mapped[str | None] = mapped_column(String(120))
    cell_range: Mapped[str | None] = mapped_column(String(40))
    included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    document: Mapped[SourceDocument] = relationship(back_populates="chunks")


class RuleDefinition(Base):
    __tablename__ = "rule_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    section_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    versions: Mapped[list["RuleVersion"]] = relationship(
        back_populates="definition", cascade="all, delete-orphan", order_by="RuleVersion.version_number"
    )


class RuleVersion(Base):
    __tablename__ = "rule_versions"
    __table_args__ = (
        UniqueConstraint("definition_id", "version_number", name="uq_rule_versions_definition_number"),
        Index("ix_rule_versions_definition_status", "definition_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    definition_id: Mapped[str] = mapped_column(ForeignKey("rule_definitions.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=RuleStatus.DRAFT.value)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False, default="local-user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    definition: Mapped[RuleDefinition] = relationship(back_populates="versions")


class BusinessCaseVersion(Base):
    __tablename__ = "business_case_versions"
    __table_args__ = (UniqueConstraint("project_id", "version_number", name="uq_case_versions_project_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("business_case_projects.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=GenerationStatus.READY.value)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    input_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    rules_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    project: Mapped[BusinessCaseProject] = relationship(back_populates="versions")
    scenarios: Mapped[list["FinancialScenario"]] = relationship(back_populates="version", cascade="all, delete-orphan")
    quality_report: Mapped["QualityReport | None"] = relationship(back_populates="version", cascade="all, delete-orphan")
    citations: Mapped[list["CitationSnapshot"]] = relationship(back_populates="version", cascade="all, delete-orphan")
    assumptions: Mapped[list["Assumption"]] = relationship(back_populates="version", cascade="all, delete-orphan")
    comments: Mapped[list["ReviewComment"]] = relationship(back_populates="version", cascade="all, delete-orphan")
    change: Mapped["VersionChange | None"] = relationship(back_populates="version", cascade="all, delete-orphan")
    validations: Mapped[list["QualityValidation"]] = relationship(back_populates="version", cascade="all, delete-orphan")
    exports: Mapped[list["ExportRecord"]] = relationship(back_populates="version", cascade="all, delete-orphan")


class FinancialScenario(Base):
    __tablename__ = "financial_scenarios"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    version_id: Mapped[str] = mapped_column(ForeignKey("business_case_versions.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    inputs_json: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[BusinessCaseVersion] = relationship(back_populates="scenarios")


class QualityReport(Base):
    __tablename__ = "quality_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    version_id: Mapped[str] = mapped_column(ForeignKey("business_case_versions.id", ondelete="CASCADE"), unique=True, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    findings_json: Mapped[str] = mapped_column(Text, nullable=False)
    compliance_json: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[BusinessCaseVersion] = relationship(back_populates="quality_report")


class CitationSnapshot(Base):
    __tablename__ = "citation_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    version_id: Mapped[str] = mapped_column(ForeignKey("business_case_versions.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(36))
    chunk_id: Mapped[str | None] = mapped_column(String(36))
    document_name: Mapped[str] = mapped_column(String(180), nullable=False)
    locator: Mapped[str] = mapped_column(String(160), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[BusinessCaseVersion] = relationship(back_populates="citations")


class Assumption(Base):
    __tablename__ = "assumptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    version_id: Mapped[str] = mapped_column(ForeignKey("business_case_versions.id", ondelete="CASCADE"), nullable=False)
    section_id: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    version: Mapped[BusinessCaseVersion] = relationship(back_populates="assumptions")


class GenerationRun(Base):
    __tablename__ = "generation_runs"
    __table_args__ = (
        Index("ix_generation_runs_project_created", "project_id", "created_at"),
        UniqueConstraint("project_id", "idempotency_key", name="uq_generation_runs_project_idempotency"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("business_case_projects.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=GenerationStatus.PREPARING.value)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    version_id: Mapped[str | None] = mapped_column(ForeignKey("business_case_versions.id", ondelete="SET NULL"))
    idempotency_key: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    project: Mapped[BusinessCaseProject] = relationship(back_populates="generation_runs")


class ReviewComment(Base):
    __tablename__ = "review_comments"
    __table_args__ = (Index("ix_review_comments_version_status", "version_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    version_id: Mapped[str] = mapped_column(ForeignKey("business_case_versions.id", ondelete="CASCADE"), nullable=False)
    section_id: Mapped[str | None] = mapped_column(String(64))
    block_id: Mapped[str | None] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    author: Mapped[str] = mapped_column(String(120), nullable=False, default="Usuario local")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[BusinessCaseVersion] = relationship(back_populates="comments")
    proposals: Mapped[list["RevisionProposal"]] = relationship(back_populates="comment", cascade="all, delete-orphan")


class RevisionProposal(Base):
    __tablename__ = "revision_proposals"
    __table_args__ = (Index("ix_revision_proposals_comment_created", "comment_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    comment_id: Mapped[str] = mapped_column(ForeignKey("review_comments.id", ondelete="CASCADE"), nullable=False)
    base_version_id: Mapped[str] = mapped_column(ForeignKey("business_case_versions.id", ondelete="CASCADE"), nullable=False)
    base_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    patch_json: Mapped[str] = mapped_column(Text, nullable=False)
    impact_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_version_id: Mapped[str | None] = mapped_column(ForeignKey("business_case_versions.id", ondelete="SET NULL"))
    comment: Mapped[ReviewComment] = relationship(back_populates="proposals")


class VersionChange(Base):
    __tablename__ = "version_changes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    version_id: Mapped[str] = mapped_column(ForeignKey("business_case_versions.id", ondelete="CASCADE"), nullable=False, unique=True)
    base_version_id: Mapped[str | None] = mapped_column(String(36))
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    author: Mapped[str] = mapped_column(String(120), nullable=False, default="Usuario local")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    changed_blocks_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    version: Mapped[BusinessCaseVersion] = relationship(back_populates="change")


class QualityValidation(Base):
    __tablename__ = "quality_validations"
    __table_args__ = (Index("ix_quality_validations_version_created", "version_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    version_id: Mapped[str] = mapped_column(ForeignKey("business_case_versions.id", ondelete="CASCADE"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rubric_version: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_model: Mapped[str] = mapped_column(String(160), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    dimension_scores_json: Mapped[str] = mapped_column(Text, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    version: Mapped[BusinessCaseVersion] = relationship(back_populates="validations")
    findings: Mapped[list["QualityFinding"]] = relationship(back_populates="validation", cascade="all, delete-orphan")


class QualityFinding(Base):
    __tablename__ = "quality_findings"
    __table_args__ = (Index("ix_quality_findings_validation_severity", "validation_id", "severity"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    validation_id: Mapped[str] = mapped_column(ForeignKey("quality_validations.id", ondelete="CASCADE"), nullable=False)
    dimension: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    section_id: Mapped[str | None] = mapped_column(String(64))
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    deterministic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    comment_id: Mapped[str | None] = mapped_column(ForeignKey("review_comments.id", ondelete="SET NULL"))
    validation: Mapped[QualityValidation] = relationship(back_populates="findings")


class ExportRecord(Base):
    __tablename__ = "export_records"
    __table_args__ = (Index("ix_export_records_version_created", "version_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    version_id: Mapped[str] = mapped_column(ForeignKey("business_case_versions.id", ondelete="CASCADE"), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    version: Mapped[BusinessCaseVersion] = relationship(back_populates="exports")
