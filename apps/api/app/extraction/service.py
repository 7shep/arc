"""Automatic graph extraction: process a source, then let the user's agent CLI read it."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.extraction.runner import (
    ExtractionFailed,
    ExtractionResult,
    ExtractionUnavailable,
    run_extraction,
)
from app.extraction.tools import AGENT_TOOLS_BY_ID, default_tool_id, detect_tools
from app.ingestion.service import DocumentProcessingError, process_document
from app.models import Document, ExtractionStatus, WorkspaceSettings, utcnow
from app.storage.base import StorageProvider

SETTINGS_ID = "default"
ERROR_LIMIT = 2_000

ExtractionRunner = Callable[..., ExtractionResult]


def get_workspace_settings(db: Session) -> WorkspaceSettings:
    """Return the single settings row, creating it with a detected agent CLI on first use."""
    settings = db.get(WorkspaceSettings, SETTINGS_ID)
    if settings is None:
        settings = WorkspaceSettings(id=SETTINGS_ID, extraction_tool_id=default_tool_id())
        db.add(settings)
        db.flush()
    return settings


def resolved_command(settings: WorkspaceSettings) -> str | None:
    """The command template to run, preferring an explicit override over the tool default."""
    if settings.extraction_command and settings.extraction_command.strip():
        return settings.extraction_command
    tool = AGENT_TOOLS_BY_ID.get(settings.extraction_tool_id or "")
    return tool.command if tool else None


def extraction_settings_view(db: Session) -> dict[str, object]:
    settings = get_workspace_settings(db)
    return {
        "enabled": settings.extraction_enabled,
        "tool_id": settings.extraction_tool_id,
        "command": resolved_command(settings),
        "command_override": settings.extraction_command,
        "tools": detect_tools(),
    }


def update_extraction_settings(
    db: Session,
    *,
    enabled: bool | None = None,
    tool_id: str | None = None,
    command: str | None = None,
    clear_command: bool = False,
) -> dict[str, object]:
    settings = get_workspace_settings(db)
    if enabled is not None:
        settings.extraction_enabled = enabled
    if tool_id is not None:
        settings.extraction_tool_id = tool_id or None
    if clear_command:
        settings.extraction_command = None
    elif command is not None:
        settings.extraction_command = command.strip() or None
    db.flush()
    return extraction_settings_view(db)


def _record(
    db: Session,
    document: Document,
    status: ExtractionStatus,
    error: str | None = None,
) -> None:
    document.extraction_status = status
    document.extraction_error = error[:ERROR_LIMIT] if error else None
    if status is ExtractionStatus.COMPLETED:
        document.extracted_at = utcnow()
    db.commit()


def extract_document(
    db: Session,
    document: Document,
    *,
    runner: ExtractionRunner | None = None,
) -> ExtractionStatus:
    """Run the configured agent CLI for one document and record the outcome on it.

    Extraction never destroys work: a missing CLI or a failing run leaves the document processed,
    its chunks intact, and the reason visible on the source row.
    """
    settings = get_workspace_settings(db)
    if not settings.extraction_enabled:
        _record(db, document, ExtractionStatus.UNAVAILABLE, "Automatic extraction is turned off")
        return ExtractionStatus.UNAVAILABLE
    command = resolved_command(settings)
    if not command:
        _record(
            db,
            document,
            ExtractionStatus.UNAVAILABLE,
            "No extraction agent is configured. Choose one in workspace settings.",
        )
        return ExtractionStatus.UNAVAILABLE

    _record(db, document, ExtractionStatus.RUNNING)
    try:
        (runner or run_extraction)(
            command_template=command,
            course_id=document.course_id,
            document_id=document.id,
        )
    except ExtractionUnavailable as error:
        _record(db, document, ExtractionStatus.UNAVAILABLE, str(error))
        return ExtractionStatus.UNAVAILABLE
    except ExtractionFailed as error:
        _record(db, document, ExtractionStatus.FAILED, str(error))
        return ExtractionStatus.FAILED
    _record(db, document, ExtractionStatus.COMPLETED)
    return ExtractionStatus.COMPLETED


def process_and_extract(
    document_id: str,
    storage: StorageProvider,
    *,
    runner: ExtractionRunner | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
) -> None:
    """Background pipeline for a freshly uploaded source: chunk it, then extract its graph.

    Runs after the upload response, so a slow agent never blocks the browser.
    """
    with session_factory() as db:
        document = db.get(Document, document_id)
        if document is None:
            return
        try:
            process_document(db, storage, document)
        except DocumentProcessingError:
            return
        if not get_settings().auto_extract:
            return
        extract_document(db, document, runner=runner)
