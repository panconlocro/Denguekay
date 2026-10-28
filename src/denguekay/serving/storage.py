"""Artifact storage port and local adapter (TB1).

The OE2 document defines Supabase Storage buckets (``modelos``, ``geodatos``,
``reportes``). TB1 uses local folders with the same logical path
``<bucket>/<name>``; a Supabase adapter can implement the same port.
"""

from pathlib import Path, PurePosixPath
from typing import Protocol

from denguekay.config.paths import STORAGE

BUCKETS = ("modelos", "geodatos", "reportes")


class Storage(Protocol):
    def save(self, path: str, content: bytes) -> None: ...
    def read(self, path: str) -> bytes: ...
    def exists(self, path: str) -> bool: ...


def validate_path(path):
    """Logical ``bucket/file`` path without directory escapes."""
    parts = PurePosixPath(path).parts
    if (len(parts) < 2 or parts[0] not in BUCKETS or any(p in ("..", ".") for p in parts)
            or "\\" in path or "//" in path or path.startswith("/")):
        raise ValueError(f"Ruta de artefacto inválida: {path}")
    return parts


class LocalStorage:
    """Save to ``models/storage/<bucket>/`` (ignored by Git)."""

    def __init__(self, root=STORAGE):
        self.root = Path(root)

    def _file(self, path):
        return self.root.joinpath(*validate_path(path))

    def save(self, path, content):
        file = self._file(path)
        file.parent.mkdir(parents=True, exist_ok=True)
        tmp = file.with_suffix(file.suffix + ".tmp")
        tmp.write_bytes(content)
        tmp.replace(file)  # atomic write: an artifact is never left half-written

    def read(self, path):
        file = self._file(path)
        if not file.is_file():
            raise FileNotFoundError(f"No existe el artefacto {path}")
        return file.read_bytes()

    def exists(self, path):
        return self._file(path).is_file()
