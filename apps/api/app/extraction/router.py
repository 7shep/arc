from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.extraction.service import extraction_settings_view, update_extraction_settings
from app.extraction.tools import AGENT_TOOLS_BY_ID
from app.schemas import ExtractionSettingsRead, ExtractionSettingsUpdate

router = APIRouter(prefix="/settings/extraction", tags=["settings"])


@router.get("", response_model=ExtractionSettingsRead)
def read_extraction_settings(db: Session = Depends(get_db)) -> Any:
    view = extraction_settings_view(db)
    db.commit()
    return view


@router.put("", response_model=ExtractionSettingsRead)
def write_extraction_settings(
    payload: ExtractionSettingsUpdate, db: Session = Depends(get_db)
) -> Any:
    if payload.tool_id and payload.tool_id not in AGENT_TOOLS_BY_ID:
        raise HTTPException(status_code=422, detail="Unknown extraction agent")
    fields = payload.model_dump(exclude_unset=True)
    view = update_extraction_settings(
        db,
        enabled=fields.get("enabled"),
        tool_id=fields.get("tool_id"),
        command=fields.get("command"),
        clear_command="command" in fields and not (fields.get("command") or "").strip(),
    )
    db.commit()
    return view
