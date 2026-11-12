"""Serve the existing local demo read-only, without using DATABASE_URL or fitting models."""

from argparse import ArgumentParser
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from sqlalchemy.engine import URL  # noqa: E402
import uvicorn  # noqa: E402

from apps.api.main import create_app  # noqa: E402
from denguekay.config.paths import DEMO_DIR, DEMO_V4_DIR  # noqa: E402
from denguekay.db.session import make_engine  # noqa: E402
from denguekay.serving.demo_database import DEMO_DB_NAME  # noqa: E402
from denguekay.serving.settings import service_settings  # noqa: E402
from denguekay.serving.storage import LocalStorage  # noqa: E402


def demo_app(folder=DEMO_DIR):
    database = (folder / DEMO_DB_NAME).resolve()
    if not database.is_file():
        raise FileNotFoundError("Falta la demo local. Prepárala con denguekay.serving.demo_database.")
    engine = make_engine(URL.create("sqlite", database=f"file:{database.as_posix()}",
                                    query={"mode": "ro", "uri": "true"}))
    cfg = replace(service_settings(), almacenamiento="local", servir_no_validadas=True)
    app = create_app(engine, cfg, api_key="", storage=LocalStorage(folder / "storage"))
    return app, engine


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--v4", action="store_true", help="Abrir la demo experimental de b3")
    parser.add_argument("--carpeta", type=Path, help="Carpeta de la demo")
    args = parser.parse_args()
    app, engine = demo_app(args.carpeta or (DEMO_V4_DIR if args.v4 else DEMO_DIR))
    try:
        uvicorn.run(app, host="127.0.0.1", port=18001, log_level="warning")
    finally:
        engine.dispose()
