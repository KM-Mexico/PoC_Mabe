import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BusinessCaseProject, BusinessCaseVersion, GenerationRun
from app.repositories.generation import GenerationRepository
from app.repositories.projects import ProjectRepository
from app.schemas import BusinessCaseVersionRead, BusinessCaseVersionSummaryRead, CitationRead, GenerationCreate, GenerationRunRead, QualityReportRead, RegenerationCreate
from app.services.generation import GenerationService

router = APIRouter(tags=["generation"])
DbSession = Annotated[Session, Depends(get_db)]


def project_or_404(db: Session, project_id: str) -> BusinessCaseProject:
    project = ProjectRepository(db).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Business case project not found")
    return project


def run_or_404(repository: GenerationRepository, run_id: str) -> GenerationRun:
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Generation run not found")
    return run


def version_or_404(repository: GenerationRepository, version_id: str) -> BusinessCaseVersion:
    version = repository.get_version(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Business case version not found")
    return version


def version_read(version: BusinessCaseVersion) -> BusinessCaseVersionRead:
    content = json.loads(version.content_json)
    quality = version.quality_report
    if quality is None:
        raise RuntimeError("Business case version has no quality report")
    return BusinessCaseVersionRead(
        id=version.id,
        project_id=version.project_id,
        version_number=version.version_number,
        status=version.status,
        table_of_contents=content["table_of_contents"],
        sections=content["sections"],
        inputs=json.loads(version.input_snapshot_json),
        rules=json.loads(version.rules_snapshot_json),
        scenarios=[{"name": scenario.name, "inputs": json.loads(scenario.inputs_json), "metrics": json.loads(scenario.metrics_json)} for scenario in version.scenarios],
        quality_report=QualityReportRead(score=quality.score, findings=json.loads(quality.findings_json), compliance=json.loads(quality.compliance_json)),
        citations=[CitationRead.model_validate(citation, from_attributes=True) for citation in version.citations],
        created_at=version.created_at,
    )


@router.post("/projects/{project_id}/generations", response_model=GenerationRunRead, status_code=status.HTTP_201_CREATED)
def create_generation(project_id: str, payload: GenerationCreate, db: DbSession, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=120)] = None) -> GenerationRunRead:
    project = project_or_404(db, project_id)
    try:
        return GenerationRunRead.model_validate(GenerationService(db).generate(project, payload, idempotency_key=idempotency_key))
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/projects/{project_id}/generations/{run_id}", response_model=GenerationRunRead)
def read_generation(project_id: str, run_id: str, db: DbSession) -> GenerationRunRead:
    project_or_404(db, project_id)
    run = run_or_404(GenerationRepository(db), run_id)
    if run.project_id != project_id:
        raise HTTPException(status_code=404, detail="Generation run not found")
    return GenerationRunRead.model_validate(run)


@router.get("/projects/{project_id}/versions", response_model=list[BusinessCaseVersionSummaryRead])
def list_versions(project_id: str, db: DbSession) -> list[BusinessCaseVersionSummaryRead]:
    project_or_404(db, project_id)
    return [BusinessCaseVersionSummaryRead(id=version.id, version_number=version.version_number, status=version.status, quality_score=version.quality_report.score if version.quality_report else 0, created_at=version.created_at) for version in GenerationRepository(db).list_versions(project_id)]


@router.get("/versions/{version_id}", response_model=BusinessCaseVersionRead)
def read_version(version_id: str, db: DbSession) -> BusinessCaseVersionRead:
    return version_read(version_or_404(GenerationRepository(db), version_id))


@router.post("/versions/{version_id}/regenerate", response_model=GenerationRunRead, status_code=status.HTTP_201_CREATED)
def regenerate_version(version_id: str, payload: RegenerationCreate, db: DbSession) -> GenerationRunRead:
    version = version_or_404(GenerationRepository(db), version_id)
    try:
        return GenerationRunRead.model_validate(GenerationService(db).regenerate(version, payload.section_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
