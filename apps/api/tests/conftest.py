import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./arc-test.db"
os.environ["UPLOAD_DIR"] = str(Path(__file__).resolve().parents[1] / "test-uploads")

from app.config import get_settings  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    upload_dir = get_settings().upload_dir
    upload_dir.mkdir(exist_ok=True)
    yield
    for file in upload_dir.iterdir():
        if file.is_file():
            file.unlink()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
