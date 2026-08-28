from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Course, Document, DocumentChunk, ProcessingStatus
from app.storage.base import StorageProvider


class CourseNotFoundError(ValueError):
    pass


class DocumentNotFoundError(ValueError):
    pass


class DocumentContentUnavailableError(ValueError):
    pass


class DocumentService:
    """Course-scoped document operations shared by HTTP and MCP entry points."""

    def __init__(self, db: Session, storage: StorageProvider) -> None:
        self.db = db
        self.storage = storage

    def require_course(self, course_id: str) -> Course:
        course = self.db.get(Course, course_id)
        if course is None:
            raise CourseNotFoundError("Course not found")
        return course

    def list_documents(self, course_id: str, *, include_processed: bool = False) -> list[Document]:
        self.require_course(course_id)
        query = select(Document).where(Document.course_id == course_id)
        if not include_processed:
            query = query.where(Document.processing_status != ProcessingStatus.READY)
        return list(self.db.scalars(query.order_by(Document.created_at)).all())

    def get_document(self, course_id: str, document_id: str) -> Document:
        self.require_course(course_id)
        document = self.db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.course_id == course_id,
            )
        )
        if document is None:
            raise DocumentNotFoundError("Document not found in course")
        return document

    def get_chunks(
        self,
        course_id: str,
        document_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> list[DocumentChunk]:
        document = self.get_document(course_id, document_id)
        chunks = list(
            self.db.scalars(
                select(DocumentChunk)
                .where(
                    DocumentChunk.course_id == course_id,
                    DocumentChunk.document_id == document_id,
                )
                .order_by(DocumentChunk.sequence)
                .offset(offset)
                .limit(limit)
            ).all()
        )
        if chunks or offset:
            return chunks
        self._chunk_text_document(document)
        return list(
            self.db.scalars(
                select(DocumentChunk)
                .where(
                    DocumentChunk.course_id == course_id,
                    DocumentChunk.document_id == document_id,
                )
                .order_by(DocumentChunk.sequence)
                .limit(limit)
            ).all()
        )

    def mark_processed(self, course_id: str, document_id: str) -> Document:
        document = self.get_document(course_id, document_id)
        document.processing_status = ProcessingStatus.READY
        document.processing_error = None
        self.db.flush()
        return document

    def report_failure(self, course_id: str, document_id: str, reason: str) -> Document:
        document = self.get_document(course_id, document_id)
        document.processing_status = ProcessingStatus.FAILED
        document.processing_error = reason
        self.db.flush()
        return document

    def _chunk_text_document(self, document: Document, chunk_size: int = 2_000) -> None:
        if Path(document.original_filename).suffix.lower() not in {".md", ".txt"}:
            raise DocumentContentUnavailableError(
                "No extracted chunks are available for this document format"
            )
        path = self.storage.get(document.storage_path)
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise DocumentContentUnavailableError("Document text could not be read") from error
        for sequence, start in enumerate(range(0, len(content), chunk_size)):
            end = min(start + chunk_size, len(content))
            self.db.add(
                DocumentChunk(
                    course_id=document.course_id,
                    document_id=document.id,
                    sequence=sequence,
                    content=content[start:end],
                    source_location={
                        "source": document.original_filename,
                        "start_offset": start,
                        "end_offset": end,
                    },
                )
            )
        self.db.flush()
