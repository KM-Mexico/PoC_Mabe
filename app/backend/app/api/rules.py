from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RuleDefinition, RuleStatus, RuleVersion
from app.repositories.rules import RuleRepository
from app.schemas import RuleCompareRead, RuleDetailRead, RuleDraftCreate, RuleDraftUpdate, RuleSummaryRead, RuleValidationRead, RuleVersionRead
from app.services.rules import validate_rule

router = APIRouter(prefix="/rules", tags=["rules"])
DbSession = Annotated[Session, Depends(get_db)]


def definition_or_404(repository: RuleRepository, section_id: str) -> RuleDefinition:
    definition = repository.get_definition(section_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Rule section not found")
    return definition


def version_or_404(repository: RuleRepository, definition: RuleDefinition, version_number: int) -> RuleVersion:
    version = repository.get_version(definition, version_number)
    if version is None:
        raise HTTPException(status_code=404, detail="Rule version not found")
    return version


def summary(definition: RuleDefinition) -> RuleSummaryRead:
    published = RuleRepository.published(definition)
    drafts = [version for version in definition.versions if version.status == RuleStatus.DRAFT.value]
    return RuleSummaryRead(
        section_id=definition.section_id,
        title=definition.title,
        ordinal=definition.ordinal,
        published_version=published.version_number if published else None,
        draft_version=max((version.version_number for version in drafts), default=None),
    )


def detail(definition: RuleDefinition) -> RuleDetailRead:
    base = summary(definition)
    published = RuleRepository.published(definition)
    return RuleDetailRead(
        **base.model_dump(),
        published=RuleVersionRead.model_validate(published) if published else None,
        versions=[RuleVersionRead.model_validate(version) for version in reversed(definition.versions)],
    )


@router.get("", response_model=list[RuleSummaryRead])
def list_rules(db: DbSession) -> list[RuleSummaryRead]:
    return [summary(definition) for definition in RuleRepository(db).list_definitions()]


@router.get("/{section_id}", response_model=RuleDetailRead)
def read_rule(section_id: str, db: DbSession) -> RuleDetailRead:
    return detail(definition_or_404(RuleRepository(db), section_id))


@router.post("/{section_id}/drafts", response_model=RuleVersionRead, status_code=status.HTTP_201_CREATED)
def create_draft(section_id: str, payload: RuleDraftCreate, db: DbSession) -> RuleVersionRead:
    repository = RuleRepository(db)
    definition = definition_or_404(repository, section_id)
    return RuleVersionRead.model_validate(repository.create_draft(definition, payload.markdown, payload.actor))


@router.put("/{section_id}/drafts/{version_number}", response_model=RuleVersionRead)
def update_draft(section_id: str, version_number: int, payload: RuleDraftUpdate, db: DbSession) -> RuleVersionRead:
    repository = RuleRepository(db)
    definition = definition_or_404(repository, section_id)
    version = version_or_404(repository, definition, version_number)
    try:
        return RuleVersionRead.model_validate(repository.update_draft(version, payload.markdown, payload.actor))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{section_id}/drafts/{version_number}/validate", response_model=RuleValidationRead)
def validate_draft(section_id: str, version_number: int, db: DbSession) -> RuleValidationRead:
    repository = RuleRepository(db)
    definition = definition_or_404(repository, section_id)
    version = version_or_404(repository, definition, version_number)
    errors = validate_rule(version.markdown, section_id)
    return RuleValidationRead(valid=not errors, errors=errors)


@router.post("/{section_id}/drafts/{version_number}/publish", response_model=RuleVersionRead)
def publish_draft(section_id: str, version_number: int, db: DbSession) -> RuleVersionRead:
    repository = RuleRepository(db)
    definition = definition_or_404(repository, section_id)
    version = version_or_404(repository, definition, version_number)
    errors = validate_rule(version.markdown, section_id)
    if errors:
        raise HTTPException(status_code=422, detail={"message": "Rule validation failed", "errors": errors})
    try:
        return RuleVersionRead.model_validate(repository.publish(definition, version))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{section_id}/restore-default", response_model=RuleVersionRead, status_code=status.HTTP_201_CREATED)
def restore_default(section_id: str, payload: RuleDraftCreate, db: DbSession) -> RuleVersionRead:
    repository = RuleRepository(db)
    definition = definition_or_404(repository, section_id)
    return RuleVersionRead.model_validate(repository.restore_default(definition, payload.actor))


@router.get("/{section_id}/compare", response_model=RuleCompareRead)
def compare_versions(section_id: str, db: DbSession, from_version: Annotated[int, Query(ge=1)], to_version: Annotated[int, Query(ge=1)]) -> RuleCompareRead:
    repository = RuleRepository(db)
    definition = definition_or_404(repository, section_id)
    try:
        diff = repository.compare(definition, from_version, to_version)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return RuleCompareRead(section_id=section_id, from_version=from_version, to_version=to_version, diff=diff)
