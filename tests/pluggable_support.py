"""Baseline of the v0 predictions written to the database, for the pluggable predictor refactor (phase 3).

``v0_database_predictions`` publishes the backend fixtures (versions, OOS and current inference for h=2
and h=4) on a temporary SQLite, runs two more inferences on past cutoffs and returns every
``prediccion`` row with the codes of the versions that produced it. The refactor must write exactly
the same rows (tests/serving/test_v0_parity.py).

XGBoost does not train bit for bit the same on every operating system, even on CPU with fixed
threads (the same limit as decision D1 of the ADR 0001). So there are two parities:

- **serving parity** (``frozen=True``): the four boosters trained with the code before the refactor
  are frozen in ``tests/fixtures/pluggable_predictor/v0_boosters/`` and the serving loads them, builds
  ServingInputs, predicts and writes ``prediccion`` and ``alerta`` without refitting. It runs everywhere;
- **full parity** (``frozen=False``): it refits the boosters, so it only runs in the environment that
  recorded the baseline (``v0_predictions_entorno.json``).

Recording, once each, refusing to overwrite (the measuring function follows the publication API; the
baselines never change):
- ``python tests/pluggable_support.py record`` wrote v0_predictions.json with the code before the
  refactor (commit 2d1c1a6; CPU, 2 threads);
- ``git worktree add <folder> 2d1c1a6`` and ``python tests/pluggable_support.py record-boosters <folder>``
  write the boosters trained with that code and the environment key of both recordings.
"""

import argparse
import base64
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
FIXTURES = TESTS / "fixtures" / "pluggable_predictor"
BASELINE = FIXTURES / "v0_predictions.json"
BOOSTERS = FIXTURES / "v0_boosters"
ENVIRONMENT = FIXTURES / "v0_predictions_entorno.json"
RECORDING_COMMIT = "2d1c1a6"
EXTRA_INFERENCES = ((4, 202540), (2, 202545))


def booster_file(horizon, task):
    return BOOSTERS / f"h{horizon}_{task}.json"


def frozen_artifacts():
    """{(horizon, task): bytes} of the boosters recorded with the code before the refactor."""
    return {(h, t): booster_file(h, t).read_bytes() for h in (2, 4) for t in ("clasificacion", "regresion")}


def environment_key():
    """What a refit depends on: operating system, XGBoost version, device and threads (cf. D1)."""
    import xgboost

    from denguekay.model.device import xgboost_settings

    setup = xgboost_settings()
    return {"sistema": platform.system(), "maquina": platform.machine(), "xgboost": xgboost.__version__,
            "configuracion": f"device={setup['device']},n_jobs={setup['n_jobs']}"}


def publish_fixtures(engine, folder, frozen=False):
    """Publish the backend fixtures as the API tests do and run the current and extra inferences.

    With ``frozen`` the versions come from the recorded boosters (no fit); otherwise they are refitted.
    """
    from dataclasses import replace

    from backend_support import datos_muestra
    from serving_support import CORTE, preparar_muestra, publish_sample
    from denguekay.db.session import transaction
    from denguekay.serving.inference import infer
    from denguekay.serving.load_data import persist_load
    from denguekay.serving.predictors import v0_compact_xgb as v0
    from denguekay.serving.storage import LocalStorage

    if frozen:
        from serving_support import protocolo_muestra
        from denguekay.serving.settings import service_settings

        cfg, protocol = service_settings(), protocolo_muestra()
        trained = v0.versions_from_boosters(protocol, (2, 4), cfg.opciones["variantes"], CORTE, frozen_artifacts())
        sample_dataset_hashes(trained)
    else:
        cfg, protocol, trained = preparar_muestra()
    data = datos_muestra(folder, cfg.seleccion_experimental)
    data = replace(data, observaciones=[o for o in data.observaciones if o["id_semana"] >= 202530])
    storage = LocalStorage(folder / "storage")
    with transaction(engine) as session:
        persist_load(session, data)
    # Since the refactor the current inference is explicit (publish --inferir); before it, publish_to_db ran it.
    publish_sample(engine, data, cfg, protocol, trained, storage, "run-paridad", "huella-paridad")
    with transaction(engine) as session:
        for horizon, cutoff in EXTRA_INFERENCES:
            infer(session, horizon, cutoff, storage=storage, servir_no_validadas=cfg.servir_no_validadas)
    return storage


def sample_dataset_hashes(trained):
    """Same sha256_dataset as ``preparar_muestra``: the test boosters were fitted on the fixture files."""
    import hashlib

    from denguekay.config.paths import BACKEND_FIXTURES

    for (h, _), prepared in trained.items():
        prepared.data["sha256_dataset"] = hashlib.sha256(
            (BACKEND_FIXTURES / f"entrenamiento_h{h}_muestra.csv").read_bytes()).hexdigest()


def v0_database_predictions(frozen=False):
    """Versions and prediction rows written by v0 on the fixtures, in a canonical order."""
    from sqlalchemy import select

    from backend_support import motor_temporal
    from denguekay.db.models import ModelVersion, Prediction, Run
    from denguekay.db.session import transaction

    with tempfile.TemporaryDirectory() as name:
        folder = Path(name)
        engine = motor_temporal(folder)
        try:
            publish_fixtures(engine, folder, frozen)
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


def v0_database_predictions_in_subprocess(frozen=False):
    """CPU with 2 threads, in a fresh process (XGBoost bits depend on device and threads)."""
    import equivalence_support as eq

    code = f"import json, pluggable_support as p; print(json.dumps(p.v0_database_predictions(frozen={frozen})))"
    process = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=eq.subprocess_env(**eq.CPU_SETUP),
                             capture_output=True, text=True, timeout=1800)
    if process.returncode != 0:
        raise RuntimeError(process.stderr[-4000:])
    return json.loads(process.stdout.strip().splitlines()[-1])


def record():
    sys.path[:0] = [str(ROOT), str(TESTS)]
    import equivalence_support as eq

    eq.write_new(BASELINE, json.dumps(v0_database_predictions_in_subprocess(), indent=1, ensure_ascii=False) + "\n")


# Runs inside a worktree of RECORDING_COMMIT: its own package and test folders come first on the path.
_RECORD_BOOSTERS = """
import base64, json, platform
import denguekay, serving_support
from denguekay.model.device import xgboost_settings
import xgboost
assert denguekay.__file__.startswith(WORKTREE), denguekay.__file__
cfg, protocol, prepared = serving_support.preparar_muestra()
setup = xgboost_settings()
print(json.dumps({"boosters": {f"h{h}_{t}.json": base64.b64encode(p.artifact).decode() for (h, t), p in prepared.items()},
                  "entorno": {"sistema": platform.system(), "maquina": platform.machine(),
                              "xgboost": xgboost.__version__,
                              "configuracion": f"device={setup['device']},n_jobs={setup['n_jobs']}"}}))
"""


def record_boosters(worktree):
    """Train the v0 boosters with the code of RECORDING_COMMIT checked out in ``worktree``; write them once."""
    sys.path[:0] = [str(ROOT), str(TESTS)]
    import equivalence_support as eq

    worktree = Path(worktree).resolve()
    head = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=worktree, capture_output=True,
                          text=True, check=True).stdout.strip()
    if head != RECORDING_COMMIT:
        raise SystemExit(f"El worktree está en {head}; debe estar en {RECORDING_COMMIT}")
    env = eq.subprocess_env(**eq.CPU_SETUP)
    env["PYTHONPATH"] = os.pathsep.join([str(worktree / "src"), str(worktree / "tests"), str(worktree)])
    code = f"WORKTREE = {str(worktree)!r}\n" + _RECORD_BOOSTERS
    process = subprocess.run([sys.executable, "-c", code], cwd=worktree, env=env,
                             capture_output=True, text=True, timeout=1800)
    if process.returncode != 0:
        raise SystemExit(process.stderr[-4000:])
    result = json.loads(process.stdout.strip().splitlines()[-1])
    for name, content in sorted(result["boosters"].items()):
        path = BOOSTERS / name
        if path.exists():
            raise SystemExit(f"{path.relative_to(ROOT)} ya existe: la línea base no se sobrescribe")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(content))
        print("escrito", path.relative_to(ROOT))
    environment = {**result["entorno"], "commit": RECORDING_COMMIT,
                   "nota": "Entorno en que se grabaron v0_predictions.json y v0_boosters/; un reentrenamiento "
                           "solo reproduce la línea base bit a bit con esta misma clave"}
    eq.write_new(ENVIRONMENT, json.dumps(environment, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("accion", choices=["record", "record-boosters"])
    parser.add_argument("worktree", nargs="?", help="record-boosters: worktree del commit 2d1c1a6")
    options = parser.parse_args()
    if options.accion == "record":
        record()
    else:
        record_boosters(options.worktree)
