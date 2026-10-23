from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from uuid import uuid4

_KEY_RE = re.compile(r"^(?:preview|export|wordbook)-[0-9a-f]{32}\.(?:csv|json|txt|pdf)$")


class WordbookStorageError(RuntimeError):
    pass


class LocalFileStorage:
    """Persist isolated wordbook artifacts with random, traversal-safe keys."""

    def __init__(self, root: str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not _KEY_RE.fullmatch(key):
            raise WordbookStorageError("Invalid wordbook storage key.")
        path = (self.root / key).resolve()
        if path.parent != self.root:
            raise WordbookStorageError("The storage path escapes the configured root.")
        return path

    async def save_bytes(self, data: bytes, *, extension: str, prefix: str) -> str:
        normalized_extension = extension.casefold().lstrip(".")
        if normalized_extension not in {"csv", "json", "txt", "pdf"}:
            raise WordbookStorageError("Unsupported wordbook artifact extension.")
        if prefix not in {"preview", "export", "wordbook"}:
            raise WordbookStorageError("Unsupported wordbook artifact prefix.")
        key = f"{prefix}-{uuid4().hex}.{normalized_extension}"
        path = self._path(key)

        def write() -> None:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            no_follow = getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags | no_follow, 0o600)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                try:
                    path.unlink(missing_ok=True)
                finally:
                    raise

        await asyncio.to_thread(write)
        return key

    async def read_bytes(self, key: str) -> bytes:
        path = self._path(key)

        def read() -> bytes:
            if path.is_symlink() or not path.is_file():
                raise WordbookStorageError("The wordbook artifact is unavailable.")
            return path.read_bytes()

        try:
            return await asyncio.to_thread(read)
        except OSError as exc:
            raise WordbookStorageError("The wordbook artifact is unavailable.") from exc

    async def delete(self, key: str | None) -> None:
        if not key:
            return
        path = self._path(key)

        def remove() -> None:
            if path.is_symlink() or path.is_file():
                path.unlink(missing_ok=True)

        await asyncio.to_thread(remove)

    def key_is_valid(self, key: str) -> bool:
        try:
            self._path(key)
        except WordbookStorageError:
            return False
        return True
