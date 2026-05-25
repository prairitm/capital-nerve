"""Persistent storage for uploaded source documents.

Today the only backend is the local filesystem. The interface is intentionally
shaped like an object store so a future S3 / GCS / Azure Blob backend can
replace it without touching ingestion, the worker, or the routers.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings


@dataclass(frozen=True)
class StoredFile:
    """Result of writing a file to the backing store."""

    storage_path: str  # opaque key (path or s3://...) — read back via `open_bytes`
    file_hash: str  # sha256 hex digest of the raw bytes
    size_bytes: int


class LocalStorage:
    """Filesystem-backed storage rooted at `settings.storage_path`.

    File names are derived from the sha256 hash so two uploads of the same
    document deduplicate naturally and the `SourceDocument.file_hash` unique
    index keeps the second row from being inserted.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or settings.storage_path
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def put_bytes(self, data: bytes, *, suffix: str = "") -> StoredFile:
        file_hash = hashlib.sha256(data).hexdigest()
        # Two-level sharding keeps a single directory from blowing up.
        sub = self._root / file_hash[:2] / file_hash[2:4]
        sub.mkdir(parents=True, exist_ok=True)
        target = sub / f"{file_hash}{suffix}"
        if not target.exists():
            target.write_bytes(data)
        return StoredFile(
            storage_path=str(target.relative_to(self._root)),
            file_hash=file_hash,
            size_bytes=len(data),
        )

    def put_bytes_at(self, data: bytes, *, path: str) -> StoredFile:
        """Write ``data`` to an explicit ``path`` relative to the storage root.

        Unlike :meth:`put_bytes` (which is content-addressed and dedupes by
        sha256), this is path-addressed: derived artefacts like rendered page
        images need a predictable layout (``page_images/<doc>/<page>.png``)
        so the extraction stage can look them up by ``DocumentPage.image_path``.
        """
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return StoredFile(
            storage_path=str(target.relative_to(self._root)),
            file_hash=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
        )

    def open_bytes(self, storage_path: str) -> bytes:
        target = self._resolve(storage_path)
        return target.read_bytes()

    def exists(self, storage_path: str) -> bool:
        return self._resolve(storage_path).exists()

    def _resolve(self, storage_path: str) -> Path:
        p = Path(storage_path)
        if p.is_absolute():
            return p
        return self._root / p


def get_storage() -> LocalStorage:
    """Single accessor so callers never instantiate `LocalStorage` directly.

    A future S3 backend swaps here based on `settings.STORAGE_DIR` scheme.
    """
    return LocalStorage()
