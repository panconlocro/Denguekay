"""Artifact storage port with a local adapter and a Supabase Storage adapter.

The OE2 document defines Supabase Storage buckets (``modelos``, ``geodatos``, ``reportes``). Both
adapters use the same logical path ``<bucket>/<name>``. ``STORAGE_BACKEND`` (or
``serving.almacenamiento`` in config.yaml) picks the adapter; see docs/backend/despliegue.md.

Supabase Storage is reached over its HTTP API with ``httpx`` (no SDK):

- upload: ``POST /storage/v1/object/{bucket}/{name}`` with ``x-upsert``;
- download from a private bucket: ``GET /storage/v1/object/authenticated/{bucket}/{name}``;
- existence: ``HEAD /storage/v1/object/{bucket}/{name}`` (the call that storage-js ``exists`` makes).

The key goes in the ``apikey`` header; a legacy key (a JWT, ``service_role``) also goes in
``Authorization: Bearer``. Downloads whose SHA-256 is known are cached in a local folder (temporary by
default; the Render filesystem is ephemeral), and a cached file is used only while its hash matches.
"""

import hashlib
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Protocol
from urllib.parse import quote

from denguekay.config.paths import STORAGE

BUCKETS = ("modelos", "geodatos", "reportes")
CACHE_FOLDER = "denguekay-storage"


class Storage(Protocol):
    def save(self, path: str, content: bytes) -> None: ...
    def read(self, path: str, sha256: str | None = None) -> bytes: ...
    def exists(self, path: str) -> bool: ...


class StorageError(RuntimeError):
    """The storage service answered with an error (the message never carries the key)."""


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

    def read(self, path, sha256=None):
        """``sha256`` is accepted for the port; the package loader checks every hash."""
        file = self._file(path)
        if not file.is_file():
            raise FileNotFoundError(f"No existe el artefacto {path}")
        return file.read_bytes()

    def exists(self, path):
        return self._file(path).is_file()


class SupabaseStorage:
    """Supabase Storage over HTTP, for private buckets, with a local cache verified by SHA-256."""

    def __init__(self, url, key, cache_dir=None, *, transport=None, timeout=30.0):
        import httpx

        url = (url or "").strip().rstrip("/")
        if not url.startswith("https://") and not url.startswith("http://"):
            raise ValueError("SUPABASE_URL debe ser la URL del proyecto (https://<ref>.supabase.co)")
        if not (key or "").strip():
            raise ValueError("Falta SUPABASE_SECRET_KEY para Supabase Storage")
        key = key.strip()
        headers = {"apikey": key}
        if key.startswith("eyJ"):  # legacy JWT key (service_role); new sb_secret_ keys are not JWTs
            headers["Authorization"] = f"Bearer {key}"
        self.cache = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir()) / CACHE_FOLDER
        self.client = httpx.Client(base_url=f"{url}/storage/v1", headers=headers, transport=transport,
                                   timeout=timeout)

    @staticmethod
    def _object(path):
        return "/".join(quote(part, safe="") for part in validate_path(path))

    def _cached(self, sha256):
        return self.cache / sha256

    def _remember(self, sha256, content):
        self.cache.mkdir(parents=True, exist_ok=True)
        file = self._cached(sha256)
        tmp = file.with_name(f"{file.name}.{os.getpid()}.tmp")
        tmp.write_bytes(content)
        tmp.replace(file)

    @staticmethod
    def _not_found(response):
        """Storage answers 404, or 400 with ``statusCode`` 404 in the body, for a missing object."""
        if response.status_code == 404:
            return True
        if response.status_code == 400:
            try:
                return str(response.json().get("statusCode")) == "404"
            except ValueError:
                return False
        return False

    @staticmethod
    def _fail(action, path, response):
        raise StorageError(f"Supabase Storage respondió {response.status_code} al {action} {path}")

    def save(self, path, content):
        content_type = "application/json" if path.endswith(".json") else "application/octet-stream"
        response = self.client.post(f"/object/{self._object(path)}", content=content,
                                    headers={"Content-Type": content_type, "x-upsert": "true"})
        if not response.is_success:
            self._fail("guardar", path, response)
        self._remember(hashlib.sha256(content).hexdigest(), content)

    def read(self, path, sha256=None):
        """Download ``path``; with ``sha256``, use and refresh the cache only for content with that hash."""
        if sha256:
            cached = self._cached(sha256)
            if cached.is_file():
                content = cached.read_bytes()
                if hashlib.sha256(content).hexdigest() == sha256:
                    return content
                cached.unlink(missing_ok=True)
        response = self.client.get(f"/object/authenticated/{self._object(path)}")
        if self._not_found(response):
            raise FileNotFoundError(f"No existe el artefacto {path}")
        if not response.is_success:
            self._fail("leer", path, response)
        content = response.content
        if sha256 and hashlib.sha256(content).hexdigest() == sha256:
            self._remember(sha256, content)
        return content

    def exists(self, path):
        response = self.client.head(f"/object/{self._object(path)}")
        if response.is_success:
            return True
        if response.status_code in (400, 404):  # a HEAD answer has no body to tell a 400 apart
            return False
        self._fail("consultar", path, response)

    def close(self):
        self.client.close()


def storage_from_environment(backend="local", environ=None):
    """Adapter chosen by ``backend``; Supabase reads ``SUPABASE_URL``, ``SUPABASE_SECRET_KEY`` and
    the optional ``STORAGE_CACHE_DIR`` from the environment (never from config.yaml)."""
    if backend == "local":
        return LocalStorage()
    if backend == "supabase":
        environ = os.environ if environ is None else environ
        return SupabaseStorage(environ.get("SUPABASE_URL"), environ.get("SUPABASE_SECRET_KEY"),
                               (environ.get("STORAGE_CACHE_DIR") or "").strip() or None)
    raise ValueError(f"Almacenamiento desconocido: {backend}")
