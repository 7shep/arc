import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./arc-test.db"
os.environ["UPLOAD_DIR"] = "./test-uploads"

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    upload_dir = Path("test-uploads")
    upload_dir.mkdir(exist_ok=True)
    yield
    for file in upload_dir.iterdir():
        if file.is_file():
            file.unlink()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
