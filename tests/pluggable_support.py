"""Baseline of the v0 predictions written to the database, for the pluggable predictor refactor (phase 3).

``v0_database_predictions`` publishes the backend fixtures (versions, OOS and current inference for h=2
and h=4) on a temporary SQLite, runs two more inferences on past cutoffs and returns every
``prediccion`` row with the codes of the versions that produced it. The refactor must write exactly
the same rows (tests/serving/test_v0_parity.py).

``python tests/pluggable_support.py record`` wrote tests/fixtures/pluggable_predictor/v0_predictions.json
once, with the code before the refactor (CPU, 2 threads); it refuses to overwrite it. The measuring
function follows the publication API; the baseline never changes.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
BASELINE = TESTS / "fixtures" / "pluggable_predictor" / "v0_predictions.json"
EXTRA_INFERENCES = ((4, 202540), (2, 202545))


def publish_fixtures(engine, folder):
    """Publish the backend fixtures as the API tests do and run the current and extra inferences."""
    from dataclasses import replace

    from backend_support import datos_muestra
    from serving_support import preparar_muestra
    from denguekay.db.session import transaction
    from denguekay.serving.inference import infer
    from denguekay.serving.load_data import persist_load
    from denguekay.serving.publish import publish_to_db
    from denguekay.serving.storage import LocalStorage

    cfg, protocol, prepared = preparar_muestra()
    data = datos_muestra(folder, cfg.seleccion_experimental)
    data = replace(data, observaciones=[o for o in data.observaciones if o["id_semana"] >= 202530])
    storage = LocalStorage(folder / "storage")
    with transaction(engine) as session:
        persist_load(session, data)
    publish_to_db(engine, data, protocol, prepared, (2, 4), cfg, "run-paridad", "huella-paridad", storage, 0)
    with transaction(engine) as session:
        for horizon, cutoff in EXTRA_INFERENCES:
            infer(session, horizon, cutoff, storage=storage, servir_no_validadas=cfg.servir_no_validadas)
    return storage


def v0_database_predictions():
    """Versions and prediction rows written by v0 on the fixtures, in a canonical order."""
    from sqlalchemy import select

    from backend_support import motor_temporal
    from denguekay.db.models import ModelVersion, Prediction, Run
    from denguekay.db.session import transaction

    with tempfile.TemporaryDirectory() as name:
        folder = Path(name)
        engine = motor_temporal(folder)
        try:
            publish_fixtures(engine, folder)
            with transaction(engine) as session:
                versions = {v.id_version: v for v in session.scalars(select(ModelVersion))}
                origins = {r.id_ejecucion: (r.detalle or {}).get("origen") for r in session.scalars(select(Run))}
                rows = [{"ubigeo": p.ubigeo, "id_semana_corte": p.id_semana_corte,
                         "id_semana_objetivo": p.id_semana_objetivo, "horizonte": p.horizonte,
                         "probabilidad_brote": p.probabilidad_brote, "nivel_riesgo": p.nivel_riesgo,
                         "casos_estimados": p.casos_estimados, "estado": p.estado,
                         "motivo_no_disponible": p.motivo_no_disponible,
                         "clasificador": versions[p.id_version_clasificador].codigo if p.id_version_clasificador else None,
                         "regresor": versions[p.id_version_regresor].codigo if p.id_version_regresor else None,
                         "origen": origins[p.id_ejecucion]}
                        for p in session.scalars(select(Prediction))]
                version_rows = [{"codigo": v.codigo, "tarea": v.tarea, "horizonte": v.horizonte,
                                 "variables": list(v.variables), "umbral_probabilidad": v.umbral_probabilidad,
                                 "cumple_umbrales": v.cumple_umbrales, "estado": v.estado}
                                for v in versions.values()]
        finally:
            engine.dispose()
    key = lambda r: (r["horizonte"], r["id_semana_corte"], r["ubigeo"])
    return {"versiones": sorted(version_rows, key=lambda v: v["codigo"]), "predicciones": sorted(rows, key=key)}


def v0_database_predictions_in_subprocess():
    """CPU with 2 threads, in a fresh process (XGBoost bits depend on device and threads)."""
    import equivalence_support as eq

    code = "import json, pluggable_support as p; print(json.dumps(p.v0_database_predictions()))"
    process = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=eq.subprocess_env(**eq.CPU_SETUP),
                             capture_output=True, text=True, timeout=1800)
    if process.returncode != 0:
        raise RuntimeError(process.stderr[-4000:])
    return json.loads(process.stdout.strip().splitlines()[-1])


def record():
    sys.path[:0] = [str(ROOT), str(TESTS)]
    import equivalence_support as eq

    eq.write_new(BASELINE, json.dumps(v0_database_predictions_in_subprocess(), indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accion", choices=["record"])
    parser.parse_args()
    record()
