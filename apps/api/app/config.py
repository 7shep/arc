import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    upload_dir: Path
    max_upload_size_mb: int
    web_origin: str
    auto_extract: bool


@lru_cache
def get_settings() -> Settings:
    repository_root = Path(__file__).resolve().parents[3]
    upload_value = Path(os.getenv("UPLOAD_DIR", "uploads"))
    upload_dir = upload_value if upload_value.is_absolute() else repository_root / upload_value
    return Settings(
        database_url=os.getenv("DATABASE_URL", "postgresql+psycopg://arc:arc@localhost:5432/arc"),
        upload_dir=upload_dir.resolve(),
        max_upload_size_mb=int(os.getenv("MAX_UPLOAD_SIZE_MB", "25")),
        web_origin=os.getenv("WEB_ORIGIN", "http://localhost:3000"),
        auto_extract=os.getenv("ARC_AUTO_EXTRACT", "1").strip().lower()
        not in {"0", "false", "no", "off"},
    )
