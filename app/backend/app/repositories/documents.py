from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EvidenceChunk, SourceDocument


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def count_for_project(self, project_id: str) -> int:
        statement = select(func.count(SourceDocument.id)).where(SourceDocument.project_id == project_id)
        return int(self.session.scalar(statement) or 0)

    def list_for_project(self, project_id: str) -> list[SourceDocument]:
        statement = select(SourceDocument).where(SourceDocument.project_id == project_id).order_by(SourceDocument.created_at.desc())
        return list(self.session.scalars(statement))

    def find_by_hash(self, project_id: str, sha256: str) -> SourceDocument | None:
        statement = select(SourceDocument).where(SourceDocument.project_id == project_id, SourceDocument.sha256 == sha256)
        return self.session.scalar(statement)

    def get(self, document_id: str) -> SourceDocument | None:
        return self.session.get(SourceDocument, document_id)

    def get_chunk(self, chunk_id: str) -> EvidenceChunk | None:
        return self.session.get(EvidenceChunk, chunk_id)

    def create(self, document: SourceDocument, chunks: list[EvidenceChunk]) -> SourceDocument:
        document.chunks = chunks
        self.session.add(document)
        self.session.commit()
        self.session.refresh(document)
        return document

    def set_document_included(self, document: SourceDocument, included: bool) -> SourceDocument:
        document.included = included
        self.session.commit()
        self.session.refresh(document)
        return document

    def set_chunk_included(self, chunk: EvidenceChunk, included: bool) -> EvidenceChunk:
        chunk.included = included
        self.session.commit()
        self.session.refresh(chunk)
        return chunk

    def delete(self, document: SourceDocument) -> None:
        self.session.delete(document)
        self.session.commit()
