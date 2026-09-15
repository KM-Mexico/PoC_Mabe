from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EvidenceChunk, SourceDocument
from app.repositories.documents import DocumentRepository
from app.repositories.projects import ProjectRepository
from app.schemas import DocumentRead, EvidenceChunkRead, InclusionUpdate, UploadBatchRead, UploadItemRead
from app.services.extractors import ExtractionError
from app.services.ingestion import MAX_BATCH_BYTES, MAX_FILES_PER_PROJECT, IngestionService
from app.services.storage import PrivateDocumentStorage

router = APIRouter(tags=["documents"])
DbSession = Annotated[Session, Depends(get_db)]


def get_project_or_404(db: Session, project_id: str) -> None:
    if ProjectRepository(db).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Business case project not found")


def get_document_or_404(repository: DocumentRepository, document_id: str) -> SourceDocument:
    document = repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    return document


def get_chunk_or_404(repository: DocumentRepository, chunk_id: str) -> EvidenceChunk:
    chunk = repository.get_chunk(chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="Evidence chunk not found")
    return chunk


def document_read(document: SourceDocument) -> DocumentRead:
    return DocumentRead(
        id=document.id,
        project_id=document.project_id,
        original_name=document.original_name,
        media_type=document.media_type,
        byte_size=document.byte_size,
        sha256=document.sha256,
        status=document.status,
        error_code=document.error_code,
        included=document.included,
        chunk_count=len(document.chunks),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.post("/projects/{project_id}/documents", response_model=UploadBatchRead, status_code=status.HTTP_201_CREATED)
async def upload_documents(
    project_id: str,
    files: Annotated[list[UploadFile], File(description="TXT, MD, PDF or XLSX documents")],
    response: Response,
    db: DbSession,
) -> UploadBatchRead:
    get_project_or_404(db, project_id)
    repository = DocumentRepository(db)
    if not files or len(files) + repository.count_for_project(project_id) > MAX_FILES_PER_PROJECT:
        raise HTTPException(status_code=413, detail="A project can contain at most 10 documents")

    payloads: list[tuple[str | None, bytes]] = []
    total_size = 0
    for upload in files:
        content = await upload.read()
        await upload.close()
        total_size += len(content)
        payloads.append((upload.filename, content))
    if total_size > MAX_BATCH_BYTES:
        raise HTTPException(status_code=413, detail="A document batch can contain at most 50 MiB")

    service = IngestionService(db)
    items: list[UploadItemRead] = []
    for file_name, content in payloads:
        safe_name = PrivateDocumentStorage.normalize_original_name(file_name)
        try:
            document = await run_in_threadpool(service.ingest, project_id, file_name, content)
            items.append(UploadItemRead(file_name=safe_name, accepted=True, document=document_read(document)))
        except ExtractionError as error:
            items.append(UploadItemRead(file_name=safe_name, accepted=False, error_code=error.code, message=str(error)))

    rejected_count = sum(not item.accepted for item in items)
    accepted_count = len(items) - rejected_count
    if rejected_count and accepted_count:
        response.status_code = status.HTTP_207_MULTI_STATUS
    elif rejected_count:
        response.status_code = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if all(item.error_code == "file_too_large" for item in items)
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
    return UploadBatchRead(accepted_count=accepted_count, rejected_count=rejected_count, items=items)


@router.get("/projects/{project_id}/documents", response_model=list[DocumentRead])
def list_documents(project_id: str, db: DbSession) -> list[DocumentRead]:
    get_project_or_404(db, project_id)
    return [document_read(document) for document in DocumentRepository(db).list_for_project(project_id)]


@router.get("/documents/{document_id}/chunks", response_model=list[EvidenceChunkRead])
def list_chunks(document_id: str, db: DbSession) -> list[EvidenceChunkRead]:
    document = get_document_or_404(DocumentRepository(db), document_id)
    return [EvidenceChunkRead.model_validate(chunk) for chunk in document.chunks]


@router.patch("/documents/{document_id}", response_model=DocumentRead)
def update_document(document_id: str, payload: InclusionUpdate, db: DbSession) -> DocumentRead:
    repository = DocumentRepository(db)
    document = get_document_or_404(repository, document_id)
    return document_read(repository.set_document_included(document, payload.included))


@router.patch("/chunks/{chunk_id}", response_model=EvidenceChunkRead)
def update_chunk(chunk_id: str, payload: InclusionUpdate, db: DbSession) -> EvidenceChunkRead:
    repository = DocumentRepository(db)
    chunk = get_chunk_or_404(repository, chunk_id)
    return EvidenceChunkRead.model_validate(repository.set_chunk_included(chunk, payload.included))


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, db: DbSession) -> Response:
    repository = DocumentRepository(db)
    document = get_document_or_404(repository, document_id)
    IngestionService(db).delete(document)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
