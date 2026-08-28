import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from docx import Document as WordDocument
from pypdf import PdfReader
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk, ProcessingStatus
from app.storage.base import StorageProvider

MAX_CHUNK_CHARS = 2_000
MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")


class DocumentProcessingError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractedChunk:
    content: str
    page_number: int | None
    section: str | None
    source_location: dict[str, Any]


def _group_units(
    units: Iterable[tuple[int, str]],
    *,
    location_type: str,
    section: str | None = None,
    page_number: int | None = None,
) -> list[ExtractedChunk]:
    chunks: list[ExtractedChunk] = []
    current: list[tuple[int, str]] = []
    current_length = 0

    def flush() -> None:
        nonlocal current, current_length
        content = "\n".join(text for _, text in current).strip()
        if content:
            location: dict[str, Any] = {
                "type": location_type,
                "start": current[0][0],
                "end": current[-1][0],
            }
            if page_number is not None:
                location["page"] = page_number
            chunks.append(
                ExtractedChunk(
                    content=content,
                    page_number=page_number,
                    section=section,
                    source_location=location,
                )
            )
        current = []
        current_length = 0

    for position, raw_text in units:
        text = raw_text.strip()
        if not text:
            continue
        pieces = [
            text[index : index + MAX_CHUNK_CHARS]
            for index in range(0, len(text), MAX_CHUNK_CHARS)
        ]
        for piece in pieces:
            added_length = len(piece) + (1 if current else 0)
            if current and current_length + added_length > MAX_CHUNK_CHARS:
                flush()
            current.append((position, piece))
            current_length += len(piece) + (1 if len(current) > 1 else 0)
    flush()
    return chunks


def _extract_text(stream: BinaryIO) -> list[ExtractedChunk]:
    text = stream.read().decode("utf-8-sig")
    return _group_units(enumerate(text.splitlines(), start=1), location_type="lines")


def _extract_markdown(stream: BinaryIO) -> list[ExtractedChunk]:
    lines = stream.read().decode("utf-8-sig").splitlines()
    chunks: list[ExtractedChunk] = []
    section: str | None = None
    section_lines: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal section_lines
        chunks.extend(_group_units(section_lines, location_type="lines", section=section))
        section_lines = []

    for line_number, line in enumerate(lines, start=1):
        heading = MARKDOWN_HEADING.match(line)
        if heading:
            flush()
            section = heading.group(1).strip()
        else:
            section_lines.append((line_number, line))
    flush()
    return chunks


def _extract_pdf(stream: BinaryIO) -> list[ExtractedChunk]:
    chunks: list[ExtractedChunk] = []
    for page_number, page in enumerate(PdfReader(stream).pages, start=1):
        text = page.extract_text() or ""
        chunks.extend(
            _group_units(
                enumerate(text.splitlines(), start=1),
                location_type="page_lines",
                page_number=page_number,
            )
        )
    return chunks


def _extract_docx(stream: BinaryIO) -> list[ExtractedChunk]:
    chunks: list[ExtractedChunk] = []
    section: str | None = None
    section_paragraphs: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal section_paragraphs
        chunks.extend(
            _group_units(section_paragraphs, location_type="paragraphs", section=section)
        )
        section_paragraphs = []

    for paragraph_number, paragraph in enumerate(WordDocument(stream).paragraphs, start=1):
        if paragraph.style.name.lower().startswith("heading"):
            flush()
            section = paragraph.text.strip() or None
        else:
            section_paragraphs.append((paragraph_number, paragraph.text))
    flush()
    return chunks


def extract_chunks(stream: BinaryIO, extension: str) -> list[ExtractedChunk]:
    extractors = {
        ".txt": _extract_text,
        ".md": _extract_markdown,
        ".pdf": _extract_pdf,
        ".docx": _extract_docx,
    }
    try:
        extractor = extractors[extension.lower()]
    except KeyError as error:
        raise ValueError(f"Unsupported document extension: {extension}") from error
    chunks = extractor(stream)
    if not chunks:
        raise ValueError("Document did not contain extractable text")
    return chunks


def start_processing(db: Session, document: Document) -> None:
    document.processing_status = ProcessingStatus.PROCESSING
    db.commit()


def complete_processing(
    db: Session, document: Document, extracted_chunks: Sequence[ExtractedChunk]
) -> list[DocumentChunk]:
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    chunks = [
        DocumentChunk(
            document_id=document.id,
            course_id=document.course_id,
            content=chunk.content,
            sequence=sequence,
            page_number=chunk.page_number,
            section=chunk.section,
            source_location=chunk.source_location,
        )
        for sequence, chunk in enumerate(extracted_chunks)
    ]
    db.add_all(chunks)
    document.processing_status = ProcessingStatus.READY
    db.commit()
    for chunk in chunks:
        db.refresh(chunk)
    return chunks


def fail_processing(db: Session, document: Document) -> None:
    db.rollback()
    document.processing_status = ProcessingStatus.FAILED
    db.commit()


def process_document(
    db: Session, storage: StorageProvider, document: Document
) -> list[DocumentChunk]:
    start_processing(db, document)
    try:
        extension = Path(document.original_filename).suffix.lower()
        with storage.open(document.storage_path) as stream:
            extracted_chunks = extract_chunks(stream, extension)
        return complete_processing(db, document, extracted_chunks)
    except Exception as error:
        fail_processing(db, document)
        raise DocumentProcessingError(str(error)) from error
