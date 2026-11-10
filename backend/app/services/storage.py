"""Storage service interface and local disk storage implementation."""
import asyncio
import re
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import settings


class StorageService(ABC):
    """Abstract interface for file storage operations."""

    @abstractmethod
    async def save_file(self, content: bytes, filename: str, user_id: int) -> str:
        """Store file content and return the persisted file path or identifier."""
        pass

    @abstractmethod
    async def read_file(self, file_path: str) -> bytes:
        """Read and return stored file bytes."""
        pass

    @abstractmethod
    async def delete_file(self, file_path: str) -> bool:
        """Delete stored file; returns True if deleted or already gone."""
        pass


class LocalStorageService(StorageService):
    """Local disk storage implementation with per-user directory isolation."""

    def __init__(self, base_dir: str = settings.LOCAL_STORAGE_DIR) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, filename: str) -> str:
        """Clean unsafe characters from filename while preserving extension."""
        clean = re.sub(r"[^\w\.-]", "_", filename)
        return clean.strip("._") or "unnamed_document"

    def _sync_write(self, target_path: Path, content: bytes) -> None:
        with open(target_path, "wb") as f:
            f.write(content)

    def _sync_read(self, path: Path) -> bytes:
        with open(path, "rb") as f:
            return f.read()

    def _sync_delete(self, path: Path) -> bool:
        if path.is_file():
            path.unlink()
            return True
        return False

    async def save_file(self, content: bytes, filename: str, user_id: int) -> str:
        """Persist file into user-scoped directory with unique prefix."""
        safe_name = self._sanitize_filename(filename)
        unique_name = f"{uuid.uuid4().hex}_{safe_name}"

        user_dir = (self.base_dir / str(user_id)).resolve()
        user_dir.mkdir(parents=True, exist_ok=True)

        target_path = (user_dir / unique_name).resolve()

        # Prevent directory traversal
        if not str(target_path).startswith(str(self.base_dir)):
            raise ValueError("Path traversal attempt detected")

        await asyncio.to_thread(self._sync_write, target_path, content)
        return str(target_path)

    async def read_file(self, file_path: str) -> bytes:
        """Read file content from local disk."""
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        return await asyncio.to_thread(self._sync_read, path)

    async def delete_file(self, file_path: str) -> bool:
        """Safely delete file from local disk."""
        try:
            path = Path(file_path).resolve()
            return await asyncio.to_thread(self._sync_delete, path)
        except Exception:
            return False


def get_storage_service() -> StorageService:
    """Dependency provider returning the configured storage backend."""
    return LocalStorageService()
