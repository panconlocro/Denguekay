"""Read the connection from the environment without exposing credentials."""

import os

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url

from denguekay.config.paths import ENV_FILE


class InvalidDatabaseSettings(ValueError):
    """The connection is missing or uses an unsupported engine."""


def get_url() -> URL:
    """Accept PostgreSQL with psycopg 3, and SQLite for local tests."""
    load_dotenv(ENV_FILE, override=False)
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value:
        raise InvalidDatabaseSettings("Falta DATABASE_URL en el entorno o en .env")
    try:
        url = make_url(value)
    except Exception:
        raise InvalidDatabaseSettings("DATABASE_URL no tiene un formato válido") from None
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername not in {"postgresql+psycopg", "sqlite", "sqlite+pysqlite"}:
        raise InvalidDatabaseSettings("DATABASE_URL debe usar PostgreSQL/psycopg o SQLite")
    if url.get_backend_name() == "postgresql" and not url.database:
        raise InvalidDatabaseSettings("DATABASE_URL debe identificar la base de datos")
    return url
