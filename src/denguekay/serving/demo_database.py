"""Demo database for the frontend (decision D1 of docs/backend/api_v1_decisiones.md).

``python -m denguekay.serving.demo_database`` builds ``models/serving/demo/``:

- ``denguekay_demo.sqlite``: SQLite migrated to head (Alembic) with the real aggregated data of Piura
  (cases and climate per district and week, no personal data), loaded and published with the same
  ``publish`` as the local backend (model versions, OOS predictions and the current inference);
- ``storage/``: the model artifacts that the published versions point to;
- ``mlflow.db`` and ``mlartifacts/``: the MLflow run of the publication, kept apart from the project's.

It only reads ``data/``. Like any publication, ``publish`` also leaves its report in
``models/serving/ejecuciones/<fingerprint>/`` (not versioned either). The demo folder is not versioned: it is
shared outside Git (Drive or a Release).
"""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

from denguekay.config.paths import ALEMBIC_CONFIG, DATA, DEMO_DIR
from denguekay.db.session import make_engine

DEMO_DB_NAME = "denguekay_demo.sqlite"
GENERATED = (DEMO_DB_NAME, "storage", "mlflow.db", "mlartifacts")


@contextmanager
def tracking_store(folder):
    """MLflow writes to the demo folder, never to the project's mlflow.db."""
    previous = os.environ.get("MLFLOW_TRACKING_URI")
    os.environ["MLFLOW_TRACKING_URI"] = f"sqlite:///{(folder / 'mlflow.db').as_posix()}"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("MLFLOW_TRACKING_URI", None)
        else:
            os.environ["MLFLOW_TRACKING_URI"] = previous


def build(destination=DEMO_DIR, replace=False):
    """Migrate an empty SQLite to head and publish v0 on it; return a summary without secrets."""
    from denguekay.serving.publish import publish
    from denguekay.serving.storage import LocalStorage

    folder = Path(destination).resolve()
    if folder.is_relative_to(DATA.resolve()):
        raise ValueError("La BD de demostración nunca se escribe en data/")
    existing = [name for name in GENERATED if (folder / name).exists()]
    if existing and not replace:
        raise FileExistsError(f"Ya existe una demo en {folder} ({', '.join(existing)}); use --reemplazar")
    for name in existing:
        path = folder / name
        shutil.rmtree(path) if path.is_dir() else path.unlink()
    folder.mkdir(parents=True, exist_ok=True)
    database = folder / DEMO_DB_NAME
    engine = make_engine(URL.create("sqlite", database=str(database)))
    try:
        config = Config(str(ALEMBIC_CONFIG))
        config.attributes["motor"] = engine
        command.upgrade(config, "head")
        with tracking_store(folder):
            summary = publish(engine, storage=LocalStorage(folder / "storage"))
    finally:
        engine.dispose()
    return {"bd": str(database), "storage": str(folder / "storage"),
            "fecha_corte_datos": summary["fecha_corte_datos"],
            "versiones": [v["codigo"] for v in summary["versiones"]],
            "inferencias_vigentes": [{k: r[k] for k in ("horizonte", "id_semana_corte", "disponibles")}
                                     for r in summary["inferencias_vigentes"]]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--salida", type=Path, default=DEMO_DIR, help="Carpeta de la demo (por defecto models/serving/demo)")
    parser.add_argument("--reemplazar", action="store_true", help="Borra la demo anterior de esa carpeta")
    options = parser.parse_args(argv)
    try:
        print(json.dumps(build(options.salida, options.reemplazar), ensure_ascii=False, default=str))
        return 0
    except (FileExistsError, ValueError) as error:
        print(f"No se generó la demo: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
