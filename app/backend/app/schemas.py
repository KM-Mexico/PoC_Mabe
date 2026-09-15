from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import DocumentStatus, GenerationStatus, ProjectStatus, RuleStatus


def normalize_required_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be blank")
    return stripped


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    organization: str = Field(min_length=1, max_length=120)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    horizon_years: int = Field(ge=1, le=10)
    discount_rate: Decimal = Field(ge=0, le=100, decimal_places=2)

    @field_validator("name", "organization")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return normalize_required_text(value)


class ProjectSetup(BaseModel):
    project_type: str = Field(default="Otro / no clasificado", min_length=1, max_length=120)
    responsible_area: str = Field(default="Por definir", min_length=1, max_length=120)
    sponsor: str = Field(min_length=1, max_length=160)
    audience: str = Field(min_length=1, max_length=300)
    decision: str = Field(min_length=1, max_length=1000)
    problem: str = Field(min_length=1, max_length=4000)
    solution: str | None = Field(default=None, max_length=4000)
    raw_idea: str | None = Field(default=None, max_length=8000)
    capture_mode: Literal["guided", "freeform"] = "guided"
    initial_investment: Decimal = Field(ge=0)
    annual_costs: list[Decimal] = Field(min_length=1, max_length=10)
    annual_benefits: list[Decimal] = Field(min_length=1, max_length=10)

    @field_validator("annual_costs", "annual_benefits")
    @classmethod
    def setup_flows_are_non_negative(cls, values: list[Decimal]) -> list[Decimal]:
        if any(value < 0 for value in values):
            raise ValueError("cash flow values must be non-negative")
        return values


class ProjectCreate(ProjectBase):
    setup: ProjectSetup | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    organization: str | None = Field(default=None, min_length=1, max_length=120)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    horizon_years: int | None = Field(default=None, ge=1, le=10)
    discount_rate: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    status: ProjectStatus | None = None
    setup: ProjectSetup | None = None

    @field_validator("name", "organization")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return normalize_required_text(value) if value is not None else None


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
    setup: ProjectSetup | None = None
    latest_quality_score: int | None = None


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    original_name: str
    media_type: str
    byte_size: int
    sha256: str
    status: DocumentStatus
    error_code: str | None
    included: bool
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class EvidenceChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    ordinal: int
    content: str
    page_number: int | None
    sheet_name: str | None
    cell_range: str | None
    included: bool


class InclusionUpdate(BaseModel):
    included: bool


class UploadItemRead(BaseModel):
    file_name: str
    accepted: bool
    document: DocumentRead | None = None
    error_code: str | None = None
    message: str | None = None


class UploadBatchRead(BaseModel):
    accepted_count: int
    rejected_count: int
    items: list[UploadItemRead]


class RuleVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version_number: int
    markdown: str
    status: str
    is_default: bool
    actor: str
    created_at: datetime
    published_at: datetime | None


class RuleSummaryRead(BaseModel):
    section_id: str
    title: str
    ordinal: int
    published_version: int | None
    draft_version: int | None


class RuleDetailRead(RuleSummaryRead):
    published: RuleVersionRead | None
    versions: list[RuleVersionRead]


class RuleDraftCreate(BaseModel):
    markdown: str | None = Field(default=None, max_length=40_000)
    actor: str = Field(default="local-user", min_length=1, max_length=120)


class RuleDraftUpdate(BaseModel):
    markdown: str = Field(min_length=1, max_length=40_000)
    actor: str = Field(default="local-user", min_length=1, max_length=120)


class RuleValidationRead(BaseModel):
    valid: bool
    errors: list[str]


class RuleCompareRead(BaseModel):
    section_id: str
    from_version: int
    to_version: int
    diff: str


class FinancialInputCreate(BaseModel):
    initial_investment: Decimal = Field(ge=0)
    annual_costs: list[Decimal] = Field(min_length=1, max_length=10)
    annual_benefits: list[Decimal] = Field(min_length=1, max_length=10)

    @field_validator("annual_costs", "annual_benefits")
    @classmethod
    def non_negative_flows(cls, values: list[Decimal]) -> list[Decimal]:
        if any(value < 0 for value in values):
            raise ValueError("cash flow values must be non-negative")
        return values


class GenerationCreate(BaseModel):
    document_kind: Literal["business_case", "blueprint"] = "business_case"
    project_type: str = Field(default="Otro / no clasificado", min_length=1, max_length=120)
    responsible_area: str = Field(default="Por definir", min_length=1, max_length=120)
    sponsor: str = Field(min_length=1, max_length=160)
    decision: str = Field(min_length=1, max_length=1000)
    problem: str = Field(min_length=1, max_length=4000)
    solution: str | None = Field(default=None, max_length=4000)
    audience: str = Field(min_length=1, max_length=300)
    financial: FinancialInputCreate
    interview_context: dict[str, str] = Field(default_factory=dict)

    @field_validator("interview_context")
    @classmethod
    def interview_answers_are_bounded(cls, values: dict[str, str]) -> dict[str, str]:
        if len(values) > 30 or any(not key.strip() or len(key) > 80 or not value.strip() or len(value) > 4_000 for key, value in values.items()):
            raise ValueError("interview context exceeds allowed limits")
        return {key.strip(): value.strip() for key, value in values.items()}


class InterviewQuestionRead(BaseModel):
    id: str
    text: str
    rationale: str
    category: str
    required: bool
    answer: str | None = None


class InterviewRead(BaseModel):
    id: str
    project_id: str
    status: Literal["collecting", "ready"]
    readiness_score: int
    summary: str
    strengths: list[str]
    gaps: list[str]
    questions: list[InterviewQuestionRead]
    answers: dict[str, str]
    answered_count: int
    remaining_question_count: int
    total_question_count: int
    topics: list[str]
    analysis_count: int
    updated_at: datetime


class InterviewAnswerCreate(BaseModel):
    question_id: str = Field(pattern=r"^[a-z0-9_\-]{1,80}$")
    answer: str = Field(min_length=1, max_length=4_000)

    @field_validator("answer")
    @classmethod
    def strip_answer(cls, value: str) -> str:
        return normalize_required_text(value)


class FinancialMetricsRead(BaseModel):
    roi_percent: Decimal | None
    npv: Decimal | None
    irr_percent: Decimal | None
    payback_years: Decimal | None
    missing_data: list[str]


class CitationRead(BaseModel):
    id: str
    document_id: str | None
    chunk_id: str | None
    document_name: str
    locator: str
    excerpt: str


class BusinessCaseSectionRead(BaseModel):
    section_id: str
    title: str
    content: str
    citation_ids: list[str]
    labels: list[str]


class QualityComplianceRead(BaseModel):
    section_id: str
    criterion: str
    result: str
    explanation: str


class QualityReportRead(BaseModel):
    score: int
    findings: list[dict[str, str]]
    compliance: list[QualityComplianceRead]


class BusinessCaseVersionRead(BaseModel):
    id: str
    project_id: str
    version_number: int
    status: str
    table_of_contents: list[dict[str, str | int]]
    sections: list[BusinessCaseSectionRead]
    inputs: dict[str, object]
    rules: list[dict[str, object]]
    scenarios: list[dict[str, object]]
    quality_report: QualityReportRead
    citations: list[CitationRead]
    created_at: datetime


class BusinessCaseVersionSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version_number: int
    status: str
    quality_score: int
    created_at: datetime


class GenerationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    status: GenerationStatus
    progress: int
    error_code: str | None
    error_message: str | None
    version_id: str | None
    created_at: datetime
    updated_at: datetime


class RegenerationCreate(BaseModel):
    section_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")


class HealthRead(BaseModel):
    status: str
    environment: str
    mocks_enabled: bool


class ProblemDetail(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str


class ReviewCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4_000)
    section_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    block_id: str | None = Field(default=None, max_length=120)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        return normalize_required_text(value)


class ReviewCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version_id: str
    section_id: str | None
    block_id: str | None
    body: str
    status: str
    author: str
    created_at: datetime
    resolved_at: datetime | None


class PatchOperation(BaseModel):
    operation: Literal["replace_text", "add_block", "remove_block", "update_assumption", "request_financial_recalculation"]
    section_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    before: str | None = Field(default=None, max_length=40_000)
    after: str | None = Field(default=None, max_length=40_000)


class RevisionProposalRead(BaseModel):
    id: str
    comment_id: str
    base_version_id: str
    status: str
    rationale: str
    patch: list[PatchOperation]
    impact: dict[str, object]
    created_at: datetime
    resolved_at: datetime | None
    applied_version_id: str | None


class ManualSectionEdit(BaseModel):
    section_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    content: str = Field(min_length=1, max_length=40_000)


class ManualRevisionCreate(BaseModel):
    base_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1, max_length=1_000)
    edits: list[ManualSectionEdit] = Field(min_length=1, max_length=16)


class VersionChangeRead(BaseModel):
    id: str
    version_id: str
    base_version_id: str | None
    source: str
    author: str
    reason: str
    changed_blocks: list[str]
    created_at: datetime


class VersionComparisonRead(BaseModel):
    from_version_id: str
    to_version_id: str
    changes: list[dict[str, object]]


class RestoreVersionCreate(BaseModel):
    reason: str = Field(default="Restaurar versión histórica", min_length=1, max_length=1_000)


class ContentHashRead(BaseModel):
    content_hash: str


class QualityFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    dimension: str
    severity: str
    section_id: str | None
    explanation: str
    action: str
    deterministic: bool
    comment_id: str | None


class QualityValidationRead(BaseModel):
    id: str
    version_id: str
    content_hash: str
    rubric_version: str
    prompt_version: str
    provider_model: str
    score: int
    threshold: int
    dimension_scores: dict[str, int]
    passed: bool
    blockers: int
    findings: list[QualityFindingRead]
    created_at: datetime


class FindingCommentCreate(BaseModel):
    instruction: str | None = Field(default=None, max_length=4_000)


class FinalizeRead(BaseModel):
    version_id: str
    status: str
    validation_id: str
    finalized_at: datetime


class ExportRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version_id: str
    format: str
    content_hash: str
    created_at: datetime
