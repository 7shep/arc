import shutil
import uuid
from pathlib import Path
from typing import BinaryIO


class LocalStorageProvider:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, stream: BinaryIO, filename: str) -> str:
        extension = Path(filename).suffix.lower()
        stored_name = f"{uuid.uuid4()}{extension}"
        destination = self.root / stored_name
        with destination.open("wb") as target:
            shutil.copyfileobj(stream, target)
        return stored_name

    def delete(self, storage_path: str) -> None:
        self.get(storage_path).unlink(missing_ok=True)

    def get(self, storage_path: str) -> Path:
        path = (self.root / storage_path).resolve()
        if self.root not in path.parents:
            raise ValueError("Invalid storage path")
        return path

    def open(self, storage_path: str) -> BinaryIO:
        return self.get(storage_path).open("rb")
