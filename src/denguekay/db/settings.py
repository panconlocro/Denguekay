"""Read the connection from the environment without exposing credentials."""

import os

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url

from denguekay.config.paths import ENV_FILE


class InvalidDatabaseSettings(ValueError):
    """The connection is missing or uses an unsupported engine."""


def get_url(variable="DATABASE_URL") -> URL:
    """Accept PostgreSQL with psycopg 3, and SQLite for local tests."""
    load_dotenv(ENV_FILE, override=False)
    value = os.environ.get(variable, "").strip()
    if not value:
        raise InvalidDatabaseSettings(f"Falta {variable} en el entorno o en .env")
    try:
        url = make_url(value)
    except Exception:
        raise InvalidDatabaseSettings(f"{variable} no tiene un formato válido") from None
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername not in {"postgresql+psycopg", "sqlite", "sqlite+pysqlite"}:
        raise InvalidDatabaseSettings(f"{variable} debe usar PostgreSQL/psycopg o SQLite")
    if url.get_backend_name() == "postgresql" and not url.database:
        raise InvalidDatabaseSettings(f"{variable} debe identificar la base de datos")
    return url


def migration_url() -> URL:
    """Alembic uses MIGRATION_DATABASE_URL (the schema owner) when it is set, else DATABASE_URL.

    In a deployment the API connects with a user that inherits rol_api, which cannot run DDL nor read
    alembic_version; the migrations need the owner (docs/backend/despliegue.md).
    """
    load_dotenv(ENV_FILE, override=False)
    return get_url("MIGRATION_DATABASE_URL" if os.environ.get("MIGRATION_DATABASE_URL", "").strip() else "DATABASE_URL")


def prepared_statements() -> bool:
    """DB_PREPARED_STATEMENTS=false turns off psycopg's automatic prepared statements.

    The Supabase shared pooler in transaction mode (port 6543) does not support them; the direct
    connection and session mode (port 5432) do.
    """
    load_dotenv(ENV_FILE, override=False)
    value = os.environ.get("DB_PREPARED_STATEMENTS", "").strip().lower()
    if value not in {"", "true", "1", "false", "0"}:
        raise InvalidDatabaseSettings("DB_PREPARED_STATEMENTS debe ser true o false")
    return value not in {"false", "0"}
