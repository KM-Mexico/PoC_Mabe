from hashlib import sha256

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import DocumentStatus, EvidenceChunk, SourceDocument
from app.repositories.documents import DocumentRepository
from app.services.extractors import DocumentExtractor, ExtractionError
from app.services.storage import PrivateDocumentStorage

MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_BATCH_BYTES = 50 * 1024 * 1024
MAX_FILES_PER_PROJECT = 10


class IngestionService:
    def __init__(self, session: Session) -> None:
        self.repository = DocumentRepository(session)
        self.extractor = DocumentExtractor()
        self.storage = PrivateDocumentStorage(get_settings().upload_directory)

    def ingest(self, project_id: str, file_name: str | None, content: bytes) -> SourceDocument:
        original_name = self.storage.normalize_original_name(file_name)
        if len(content) > MAX_FILE_BYTES:
            raise ExtractionError("file_too_large", "Each file must be 15 MiB or smaller.")
        if not content:
            raise ExtractionError("empty_document", "The file is empty.")
        digest = sha256(content).hexdigest()
        if self.repository.find_by_hash(project_id, digest):
            raise ExtractionError("duplicate_document", "This document is already attached to the project.")

        result = self.extractor.extract(original_name, content)
        storage_name = self.storage.write(content)
        document = SourceDocument(
            project_id=project_id,
            original_name=original_name,
            storage_name=storage_name,
            media_type=result.media_type,
            byte_size=len(content),
            sha256=digest,
            status=result.status.value,
            included=result.status == DocumentStatus.READY,
        )
        chunks = [
            EvidenceChunk(
                ordinal=ordinal,
                content=chunk.content,
                page_number=chunk.page_number,
                sheet_name=chunk.sheet_name,
                cell_range=chunk.cell_range,
            )
            for ordinal, chunk in enumerate(result.chunks)
        ]
        try:
            return self.repository.create(document, chunks)
        except Exception:
            self.storage.delete(storage_name)
            raise

    def delete(self, document: SourceDocument) -> None:
        storage_name = document.storage_name
        self.repository.delete(document)
        self.storage.delete(storage_name)
