"""Serve the existing local v2 demo read-only, without using DATABASE_URL or fitting models."""

from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from sqlalchemy.engine import URL  # noqa: E402
import uvicorn  # noqa: E402

from apps.api.main import create_app  # noqa: E402
from denguekay.config.paths import DEMO_DIR  # noqa: E402
from denguekay.db.session import make_engine  # noqa: E402
from denguekay.serving.demo_database import DEMO_DB_NAME  # noqa: E402
from denguekay.serving.settings import service_settings  # noqa: E402
from denguekay.serving.storage import LocalStorage  # noqa: E402


def demo_app():
    database = (DEMO_DIR / DEMO_DB_NAME).resolve()
    if not database.is_file():
        raise FileNotFoundError("Falta la demo local. Prepárala con denguekay.serving.demo_database.")
    engine = make_engine(URL.create("sqlite", database=f"file:{database.as_posix()}",
                                    query={"mode": "ro", "uri": "true"}))
    cfg = replace(service_settings(), almacenamiento="local", servir_no_validadas=True)
    app = create_app(engine, cfg, api_key="", storage=LocalStorage(DEMO_DIR / "storage"))
    return app, engine


if __name__ == "__main__":
    app, engine = demo_app()
    try:
        uvicorn.run(app, host="127.0.0.1", port=18001, log_level="warning")
    finally:
        engine.dispose()
