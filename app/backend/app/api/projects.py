from typing import Annotated
import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.projects import ProjectRepository
from app.repositories.documents import DocumentRepository
from app.schemas import ProjectCreate, ProjectRead, ProjectSetup, ProjectUpdate
from app.services.ingestion import IngestionService

router = APIRouter(prefix="/projects", tags=["projects"])
DbSession = Annotated[Session, Depends(get_db)]


def get_or_404(repository: ProjectRepository, project_id: str):
    project = repository.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Business case project not found")
    return project


def project_read(project, latest_quality_score: int | None = None) -> ProjectRead:
    result = ProjectRead.model_validate(project)
    result.latest_quality_score = latest_quality_score
    if project.setup_json:
        result.setup = ProjectSetup.model_validate(json.loads(project.setup_json))
    return result


@router.get("", response_model=list[ProjectRead])
def list_projects(db: DbSession) -> list[ProjectRead]:
    repository = ProjectRepository(db)
    projects = repository.list()
    scores = repository.latest_quality_scores([project.id for project in projects])
    return [project_read(item, scores.get(item.id)) for item in projects]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: DbSession) -> ProjectRead:
    return project_read(ProjectRepository(db).create(payload))


@router.get("/{project_id}", response_model=ProjectRead)
def read_project(project_id: str, db: DbSession) -> ProjectRead:
    repository = ProjectRepository(db)
    return project_read(get_or_404(repository, project_id), repository.latest_quality_scores([project_id]).get(project_id))


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(project_id: str, payload: ProjectUpdate, db: DbSession) -> ProjectRead:
    repository = ProjectRepository(db)
    return project_read(repository.update(get_or_404(repository, project_id), payload), repository.latest_quality_scores([project_id]).get(project_id))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: DbSession) -> Response:
    repository = ProjectRepository(db)
    project = get_or_404(repository, project_id)
    document_service = IngestionService(db)
    for document in DocumentRepository(db).list_for_project(project_id):
        document_service.delete(document)
    repository.delete(project)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
