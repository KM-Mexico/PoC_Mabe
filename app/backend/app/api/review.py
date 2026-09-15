import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.generation import version_or_404, version_read
from app.database import get_db
from app.repositories.generation import GenerationRepository
from app.schemas import BusinessCaseVersionRead, ContentHashRead, ManualRevisionCreate, RestoreVersionCreate, ReviewCommentCreate, ReviewCommentRead, RevisionProposalRead, VersionChangeRead, VersionComparisonRead
from app.services.review import ReviewService

router = APIRouter(tags=["review"])
DbSession = Annotated[Session, Depends(get_db)]


def proposal_read(item) -> RevisionProposalRead:
    return RevisionProposalRead(id=item.id, comment_id=item.comment_id, base_version_id=item.base_version_id, status=item.status, rationale=item.rationale, patch=json.loads(item.patch_json), impact=json.loads(item.impact_json), created_at=item.created_at, resolved_at=item.resolved_at, applied_version_id=item.applied_version_id)


@router.get("/versions/{version_id}/content-hash", response_model=ContentHashRead)
def read_content_hash(version_id: str, db: DbSession) -> ContentHashRead:
    version = version_or_404(GenerationRepository(db), version_id)
    return ContentHashRead(content_hash=ReviewService.content_hash(version))


@router.post("/versions/{version_id}/comments", response_model=ReviewCommentRead, status_code=status.HTTP_201_CREATED)
def create_comment(version_id: str, payload: ReviewCommentCreate, db: DbSession) -> ReviewCommentRead:
    version = version_or_404(GenerationRepository(db), version_id)
    try:
        return ReviewCommentRead.model_validate(ReviewService(db).create_comment(version, payload))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/versions/{version_id}/comments", response_model=list[ReviewCommentRead])
def list_comments(version_id: str, db: DbSession, comment_status: Annotated[Literal["open", "resolved", "rejected"] | None, Query(alias="status")] = None) -> list[ReviewCommentRead]:
    version_or_404(GenerationRepository(db), version_id)
    return [ReviewCommentRead.model_validate(item) for item in ReviewService(db).list_comments(version_id, comment_status)]


@router.post("/comments/{comment_id}/proposal", response_model=RevisionProposalRead, status_code=status.HTTP_201_CREATED)
def create_proposal(comment_id: str, db: DbSession) -> RevisionProposalRead:
    service = ReviewService(db)
    comment = service.get_comment(comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Review comment not found")
    try:
        return proposal_read(service.create_proposal(comment))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/proposals/{proposal_id}", response_model=RevisionProposalRead)
def read_proposal(proposal_id: str, db: DbSession) -> RevisionProposalRead:
    proposal = ReviewService(db).get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Revision proposal not found")
    return proposal_read(proposal)


@router.post("/proposals/{proposal_id}/accept", response_model=BusinessCaseVersionRead, status_code=status.HTTP_201_CREATED)
def accept_proposal(proposal_id: str, db: DbSession) -> BusinessCaseVersionRead:
    service = ReviewService(db)
    proposal = service.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Revision proposal not found")
    try:
        return version_read(service.accept(proposal))
    except ValueError as error:
        raise HTTPException(status_code=409 if "obsolete" in str(error) else 422, detail=str(error)) from error


@router.post("/proposals/{proposal_id}/reject", response_model=RevisionProposalRead)
def reject_proposal(proposal_id: str, db: DbSession) -> RevisionProposalRead:
    service = ReviewService(db)
    proposal = service.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Revision proposal not found")
    try:
        return proposal_read(service.reject(proposal))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/versions/{version_id}/manual-revision", response_model=BusinessCaseVersionRead, status_code=status.HTTP_201_CREATED)
def manual_revision(version_id: str, payload: ManualRevisionCreate, db: DbSession) -> BusinessCaseVersionRead:
    base = version_or_404(GenerationRepository(db), version_id)
    try:
        return version_read(ReviewService(db).manual_revision(base, payload))
    except ValueError as error:
        raise HTTPException(status_code=409 if "Base version changed" in str(error) else 422, detail=str(error)) from error


@router.get("/projects/{project_id}/version-comparison", response_model=VersionComparisonRead)
def compare_versions(project_id: str, from_version: str, to_version: str, db: DbSession) -> VersionComparisonRead:
    repository = GenerationRepository(db)
    first, second = version_or_404(repository, from_version), version_or_404(repository, to_version)
    if first.project_id != project_id or second.project_id != project_id:
        raise HTTPException(status_code=404, detail="Version not found in project")
    return VersionComparisonRead(from_version_id=first.id, to_version_id=second.id, changes=ReviewService(db).comparison(first, second))


@router.post("/versions/{version_id}/restore", response_model=BusinessCaseVersionRead, status_code=status.HTTP_201_CREATED)
def restore_version(version_id: str, payload: RestoreVersionCreate, db: DbSession) -> BusinessCaseVersionRead:
    historical = version_or_404(GenerationRepository(db), version_id)
    return version_read(ReviewService(db).restore(historical, payload.reason))


@router.get("/projects/{project_id}/version-changes", response_model=list[VersionChangeRead])
def version_changes(project_id: str, db: DbSession) -> list[VersionChangeRead]:
    return [VersionChangeRead(id=item.id, version_id=item.version_id, base_version_id=item.base_version_id, source=item.source, author=item.author, reason=item.reason, changed_blocks=json.loads(item.changed_blocks_json), created_at=item.created_at) for item in ReviewService(db).history(project_id)]
