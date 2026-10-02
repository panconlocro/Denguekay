"""Lee la conexión desde el entorno sin exponer credenciales."""

import os

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url

from src.utils.paths import ENV_FILE


class ConfiguracionBDInvalida(ValueError):
    """La conexión falta o utiliza un motor no admitido."""


def obtener_url() -> URL:
    """Admite PostgreSQL con psycopg 3 y SQLite para pruebas locales."""
    load_dotenv(ENV_FILE, override=False)
    valor = os.environ.get("DATABASE_URL", "").strip()
    if not valor:
        raise ConfiguracionBDInvalida("Falta DATABASE_URL en el entorno o en .env")
    try:
        url = make_url(valor)
    except Exception:
        raise ConfiguracionBDInvalida("DATABASE_URL no tiene un formato válido") from None
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername not in {"postgresql+psycopg", "sqlite", "sqlite+pysqlite"}:
        raise ConfiguracionBDInvalida("DATABASE_URL debe usar PostgreSQL/psycopg o SQLite")
    if url.get_backend_name() == "postgresql" and not url.database:
        raise ConfiguracionBDInvalida("DATABASE_URL debe identificar la base de datos")
    return url
