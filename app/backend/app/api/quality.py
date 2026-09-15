import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.generation import version_or_404
from app.database import get_db
from app.repositories.generation import GenerationRepository
from app.schemas import ExportRecordRead, FinalizeRead, FindingCommentCreate, QualityFindingRead, QualityValidationRead, ReviewCommentRead
from app.services.quality import QualityService
from app.services.review import ReviewService

router = APIRouter(tags=["quality"])
DbSession = Annotated[Session, Depends(get_db)]


def validation_read(item, threshold: int) -> QualityValidationRead:
    findings = [QualityFindingRead.model_validate(finding) for finding in item.findings]
    return QualityValidationRead(
        id=item.id, version_id=item.version_id, content_hash=item.content_hash, rubric_version=item.rubric_version,
        prompt_version=item.prompt_version, provider_model=item.provider_model, score=item.score, threshold=threshold,
        dimension_scores=json.loads(item.dimension_scores_json), passed=item.passed,
        blockers=sum(finding.severity == "bloqueante" for finding in item.findings), findings=findings, created_at=item.created_at,
    )


@router.post("/versions/{version_id}/validations", response_model=QualityValidationRead, status_code=status.HTTP_201_CREATED)
def create_validation(version_id: str, db: DbSession) -> QualityValidationRead:
    version = version_or_404(GenerationRepository(db), version_id)
    service = QualityService(db)
    try:
        return validation_read(service.validate(version), service.settings.quality_score_threshold)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/versions/{version_id}/validations", response_model=list[QualityValidationRead])
def list_validations(version_id: str, db: DbSession) -> list[QualityValidationRead]:
    version_or_404(GenerationRepository(db), version_id)
    service = QualityService(db)
    return [validation_read(item, service.settings.quality_score_threshold) for item in service.history(version_id)]


@router.post("/findings/{finding_id}/comments", response_model=ReviewCommentRead, status_code=status.HTTP_201_CREATED)
def finding_comment(finding_id: str, payload: FindingCommentCreate, db: DbSession) -> ReviewCommentRead:
    service = QualityService(db)
    finding = service.get_finding(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Quality finding not found")
    try:
        return ReviewCommentRead.model_validate(service.finding_to_comment(finding, payload.instruction))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/versions/{version_id}/finalize", response_model=FinalizeRead)
def finalize_version(version_id: str, db: DbSession) -> FinalizeRead:
    version = version_or_404(GenerationRepository(db), version_id)
    service = QualityService(db)
    try:
        validation, finalized_at = service.finalize(version)
        return FinalizeRead(version_id=version.id, status=version.status, validation_id=validation.id, finalized_at=finalized_at)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/versions/{version_id}/exports", response_model=list[ExportRecordRead])
def list_exports(version_id: str, db: DbSession) -> list[ExportRecordRead]:
    version_or_404(GenerationRepository(db), version_id)
    return [ExportRecordRead.model_validate(item) for item in QualityService(db).exports(version_id)]


@router.get("/versions/{version_id}/exports/{export_format}")
def export_version(version_id: str, export_format: Literal["json", "markdown", "pdf"], db: DbSession) -> Response:
    version = version_or_404(GenerationRepository(db), version_id)
    service = QualityService(db)
    try:
        body, media_type, extension, _record = service.export(version, export_format)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    disposition = "inline" if export_format == "pdf" else "attachment"
    return Response(content=body, media_type=media_type, headers={"Content-Disposition": f'{disposition}; filename="business-case-v{version.version_number}.{extension}"', "X-Content-Hash": ReviewService.content_hash(version)})
