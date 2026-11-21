"""Initial fill of ``emision_prediccion`` (the insert-only first emission) from what was emitted before it existed.

``python -m denguekay.serving.first_emission_backfill`` reads ``DATABASE_URL`` and, per cutoff week of the weekly update
that has no first emission yet:

1. takes the OLDEST archived emission of the cutoff (``<base>/<cutoff>/<stamp>/``, ``emision.json`` and
   ``predicciones.csv``, written before the outcomes were known) and inserts its forecasts with
   ``procedencia = 'archivo'``, its emission instant and the last week the Sala had published at that moment;
2. if the cutoff has no archive (or the archived run is not in this database), inserts the CURRENT row of ``prediccion``
   of the weekly update with ``procedencia = 'prediccion_actual'`` and an unknown last published week: it may already be
   a re-emission, so it is never eligible for the prospective evaluation.

Insert-only and idempotent: it never modifies a first emission that exists, and it never reads ``data/``. The archive
copied to the Storage by the weekly runner (``reportes/emisiones/<cutoff>/<stamp>/``) is used by downloading that
folder and passing it as ``--carpeta``. ``--sin-escribir`` only reports.
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

import pandas as pd
from sqlalchemy import select

from denguekay.config.paths import SERVING_WEEKLY
from denguekay.db.models import FirstEmission, Prediction, Run
from denguekay.db.session import make_engine, transaction, upsert
from denguekay.serving import emissions

COLUMNS = ["ubigeo", "horizonte", "id_semana_objetivo", "probabilidad_brote", "nivel_riesgo", "casos_estimados",
           "estado", "motivo_no_disponible"]


def _clean(value):
    return None if pd.isna(value) else value


def archived_emissions(base):
    """{cutoff: folder of its oldest archived emission}; the folder names are UTC stamps that sort by time."""
    oldest = {}
    base = Path(base)
    if not base.is_dir():
        return oldest
    for cutoff_folder in sorted(p for p in base.iterdir() if p.is_dir() and p.name.isdigit()):
        stamps = sorted(p for p in cutoff_folder.iterdir()
                        if (p / "emision.json").is_file() and (p / "predicciones.csv").is_file())
        if stamps:
            oldest[int(cutoff_folder.name)] = stamps[0]
    return oldest


def rows_from_archive(folder, existing_runs):
    """First-emission rows of an archived emission, or ``None`` if one of its runs is not in the database."""
    record = json.loads((folder / "emision.json").read_text(encoding="utf-8"))
    runs = {int(h): run for h, run in record["ejecuciones"]["inferencias"].items()}
    if not set(runs.values()) <= existing_runs:
        return None
    frame = pd.read_csv(folder / "predicciones.csv", dtype={"ubigeo": "string"})
    emitted = datetime.fromisoformat(record["emitida_utc"])
    return [{"ubigeo": str(row["ubigeo"]).zfill(6), "id_semana_corte": record["id_semana_corte"],
             "horizonte": int(row["horizonte"]), "id_semana_objetivo": int(row["id_semana_objetivo"]),
             **{name: _clean(row[name]) for name in COLUMNS[3:]}, "id_ejecucion": runs[int(row["horizonte"])],
             "fecha_emision": emitted, "ultima_semana_sala_publicada": record["ultima_semana_sala_publicada"],
             "procedencia": "archivo"} for _, row in frame.iterrows()]


def rows_from_current(sesion, cutoff):
    """First-emission rows from the current ``prediccion`` rows of the weekly update of a cutoff."""
    query = select(Prediction, Run.detalle).join(Run, Run.id_ejecucion == Prediction.id_ejecucion).where(
        Prediction.id_semana_corte == cutoff)
    return [{"ubigeo": p.ubigeo, "id_semana_corte": p.id_semana_corte, "horizonte": p.horizonte,
             "id_semana_objetivo": p.id_semana_objetivo, "probabilidad_brote": p.probabilidad_brote,
             "nivel_riesgo": p.nivel_riesgo, "casos_estimados": p.casos_estimados, "estado": p.estado,
             "motivo_no_disponible": p.motivo_no_disponible, "id_ejecucion": p.id_ejecucion,
             "fecha_emision": p.fecha_generacion, "ultima_semana_sala_publicada": None,
             "procedencia": "prediccion_actual"}
            for p, detail in sesion.execute(query).all() if (detail or {}).get("origen") == emissions.ORIGIN]


def backfill(sesion, base=emissions.EMISSIONS, *, write=True):
    """Fill the cutoffs without a first emission and return what was (or would be) inserted, per origin."""
    weekly_cutoffs = sorted({run.id_semana_corte for run in sesion.scalars(select(Run).where(
        Run.tipo == "inferencia", Run.estado == "exitosa")) if (run.detalle or {}).get("origen") == emissions.ORIGIN})
    done = set(sesion.scalars(select(FirstEmission.id_semana_corte).distinct()))
    existing_runs = set(sesion.scalars(select(Run.id_ejecucion)))
    archives = archived_emissions(base)
    report = {"cortes": {}, "filas": {"archivo": 0, "prediccion_actual": 0}}
    for cutoff in weekly_cutoffs:
        if cutoff in done:
            report["cortes"][str(cutoff)] = "ya tenía primera emisión"
            continue
        rows = rows_from_archive(archives[cutoff], existing_runs) if cutoff in archives else None
        rows = rows if rows is not None else rows_from_current(sesion, cutoff)
        if not rows:
            report["cortes"][str(cutoff)] = "sin predicciones del update semanal"
            continue
        origin = rows[0]["procedencia"]
        report["cortes"][str(cutoff)] = origin
        report["filas"][origin] += len(rows)
        if write:
            upsert(sesion, FirstEmission.__table__, rows, emissions.FIRST_EMISSION_KEY, update=())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--carpeta", type=Path, default=SERVING_WEEKLY / "emisiones",
                        help="Carpeta con <corte>/<marca>/ (por defecto, la de las emisiones locales)")
    parser.add_argument("--sin-escribir", action="store_true", help="Solo informa lo que insertaría")
    args = parser.parse_args(argv)
    engine = make_engine()
    try:
        with transaction(engine) as sesion:
            report = backfill(sesion, args.carpeta, write=not args.sin_escribir)
    finally:
        engine.dispose()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
