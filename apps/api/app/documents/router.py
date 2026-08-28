from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.graph.service import SqlCourseGraph
from app.ingestion.service import DocumentProcessingError, process_document
from app.models import (
    REVIEWABLE_STATUSES,
    Course,
    Document,
    DocumentChunk,
    DocumentType,
)
from app.schemas import DocumentChunkRead, DocumentGraphRead, DocumentRead
from app.storage.base import StorageProvider
from app.storage.local import LocalStorageProvider

router = APIRouter(prefix="/courses/{course_id}/documents", tags=["documents"])
ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt", ".docx"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/markdown",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/octet-stream",
}


def get_storage_provider() -> StorageProvider:
    return LocalStorageProvider(get_settings().upload_dir)


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(
    course_id: str,
    document_type: DocumentType = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Document:
    if not db.get(Course, course_id):
        raise HTTPException(status_code=404, detail="Course not found")
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()
    if not original_name or extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Supported files: .pdf, .md, .txt, .docx")
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported file content type")
    settings = get_settings()
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413, detail=f"File exceeds {settings.max_upload_size_mb} MB"
        )
    storage = get_storage_provider()
    storage_path = storage.save(file.file, original_name)
    document = Document(
        course_id=course_id,
        filename=storage_path,
        original_filename=original_name,
        document_type=document_type,
        mime_type=file.content_type or "application/octet-stream",
        storage_path=storage_path,
    )
    db.add(document)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(storage_path)
        raise
    db.refresh(document)
    return document


def _chunk_counts(db: Session, course_id: str) -> dict[str, int]:
    rows = db.execute(
        select(DocumentChunk.document_id, func.count(DocumentChunk.id))
        .where(DocumentChunk.course_id == course_id)
        .group_by(DocumentChunk.document_id)
    ).all()
    return {document_id: count for document_id, count in rows}


@router.get("", response_model=list[DocumentRead])
def list_documents(course_id: str, db: Session = Depends(get_db)) -> list[DocumentRead]:
    if not db.get(Course, course_id):
        raise HTTPException(status_code=404, detail="Course not found")
    documents = db.scalars(
        select(Document)
        .where(Document.course_id == course_id)
        .order_by(Document.created_at.desc())
    ).all()
    counts = _chunk_counts(db, course_id)
    return [
        DocumentRead.model_validate(
            {**document.__dict__, "chunk_count": counts.get(document.id, 0)}
        )
        for document in documents
    ]


def _get_document(db: Session, course_id: str, document_id: str) -> Document:
    document = db.scalar(
        select(Document).where(Document.id == document_id, Document.course_id == course_id)
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.post("/{document_id}/process", response_model=DocumentRead)
def process_uploaded_document(
    course_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    storage: StorageProvider = Depends(get_storage_provider),
) -> DocumentRead:
    document = _get_document(db, course_id, document_id)
    try:
        chunks = process_document(db, storage, document)
    except DocumentProcessingError as error:
        raise HTTPException(
            status_code=422, detail=f"Document processing failed: {error}"
        ) from error
    db.refresh(document)
    return DocumentRead.model_validate({**document.__dict__, "chunk_count": len(chunks)})


@router.get("/{document_id}/graph", response_model=DocumentGraphRead)
def get_document_graph(
    course_id: str, document_id: str, db: Session = Depends(get_db)
) -> DocumentGraphRead:
    """Approved graph records this document is the evidence for, plus its review backlog."""
    _get_document(db, course_id, document_id)
    graph = SqlCourseGraph(db)
    nodes, relationships = graph.get_document_records(course_id, document_id)
    pending = len(
        graph.list_candidate_nodes(
            course_id, statuses=REVIEWABLE_STATUSES, document_id=document_id
        )
    ) + len(
        graph.list_candidate_relationships(
            course_id, statuses=REVIEWABLE_STATUSES, document_id=document_id
        )
    )
    chunk_count = (
        db.scalar(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.document_id == document_id
            )
        )
        or 0
    )
    return DocumentGraphRead.model_validate(
        {
            "document_id": document_id,
            "nodes": nodes,
            "edges": relationships,
            "chunk_count": chunk_count,
            "pending_candidate_count": pending,
        }
    )


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkRead])
def list_document_chunks(
    course_id: str, document_id: str, db: Session = Depends(get_db)
) -> list[DocumentChunk]:
    _get_document(db, course_id, document_id)
    return list(
        db.scalars(
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.course_id == course_id,
            )
            .order_by(DocumentChunk.sequence)
        ).all()
    )
