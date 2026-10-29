"""Fixtures of the v2 serving (phase 4 of docs/backend/prompt_api_v1.md), apart from every earlier fixture.

``data/`` is not in Git, so the CI has no gold. ``tests/fixtures/v2_serving/`` holds, recorded once:

- the database inputs of 6 districts, 2017–2025 (real aggregated data): ``panel_muestra.csv`` (integrated
  silver), ``cobertura_muestra.csv``, ``etiquetas_muestra.csv`` (gold h=2: cases, label and threshold) and
  ``sala_muestra.csv`` (2025), with ``procedencia.json``;
- what the frozen configuration computes on the **full** data with the code before phase 4 (commit
  ab8503b, CPU with 2 threads): ``origenes_muestra.csv`` (``frozen_configs.origins``: base_6, B3, A3 and the
  targets), ``predicciones_muestra.csv`` (``frozen_configs.predict`` of every block plus the chronological
  Platt of ``calibrate_chronologically``) for those districts;
- the model of block ``calendario_2025`` trained on the full gold (``paquete_calendario_2025/``: booster,
  its α and the Platt of that block) and ``entorno.json`` (the recording environment key).

Each district's variables only depend on its own series (base_6, B3 own history, A3 of its climate, the
threshold of its weeks), so the subset gives an exact parity. Recording, refusing to overwrite:
``git worktree add <folder> ab8503b`` and ``python tests/v2_support.py record <folder>``.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
FIXTURES = TESTS / "fixtures" / "v2_serving"
PACKAGE = FIXTURES / "paquete_calendario_2025"
ENVIRONMENT = FIXTURES / "entorno.json"
RECORDING_COMMIT = "ab8503b"
DISTRICTS = ("200101", "200104", "200201", "200204", "200502", "200601")
DISTRICT_RULE = ("los 3 distritos de tests/fixtures/backend (200101, 200201, 200502), uno que nunca tuvo casos "
                 "(200204) y los dos con más casos en 2023 después de 200101 (200104 y 200601)")
PARITY_BLOCK = ("calendario_2025", "calendario", 2025)
FIRST_2022_TARGET_CUTOFF = "2021-12-25"  # first origin whose t+2 is in 2022 (decision M4: no history before 2017)
SERVICE_CUTOFF = "2025-12-27"  # last closed week of the fixtures
ORIGIN_COLUMNS_EXTRA = ["log_poblacion_censo_2017"]
DATE_COLUMNS = ("semana_inicio", "origen_cierre", "origen_inicio", "semana_inicio_h2", "semana_inicio_h3",
                "semana_inicio_h4")


def read(name):
    import pandas as pd

    # round_trip: the recorded floats are read back bit for bit (the default parser can be off by one ulp).
    data = pd.read_csv(FIXTURES / name, dtype={"ubigeo": "string"}, float_precision="round_trip")
    for column in DATE_COLUMNS:
        if column in data:
            data[column] = pd.to_datetime(data[column])
    return data


def origins():
    return read("origenes_muestra.csv")


def predictions():
    return read("predicciones_muestra.csv")


def package_meta():
    return json.loads((PACKAGE / "meta.json").read_text(encoding="utf-8"))


def frozen_fit():
    """The calendario_2025 block model as a ``FrozenFit`` (booster, α and Platt per horizon)."""
    from denguekay.serving.predictors.v2_e3_s4 import FrozenFit

    meta = package_meta()
    return FrozenFit((PACKAGE / "booster.json").read_bytes(), {int(h): a for h, a in meta["alfa"].items()},
                     {int(h): c for h, c in meta["platt"].items()})


def options():
    return {"configuracion": "v2", "nivel_intervalo": 0.80}


def sample_prepared():
    """``Prepared`` of the v2 builder from the fixtures (the 6 districts) instead of the full data."""
    from denguekay.model.registry import configuration
    from denguekay.serving.predictors.v2_e3_s4 import Prepared

    procedencia = json.loads((FIXTURES / "procedencia.json").read_text(encoding="utf-8"))
    keys = ["ubigeo", "anio", "semana"]
    series = read("panel_muestra.csv")[[*keys, "semana_inicio"]].merge(
        read("etiquetas_muestra.csv")[[*keys, "casos_Dengue", "brote"]], on=keys, validate="one_to_one")
    hashes = {f"v2_muestra:{n}": hashlib.sha256((FIXTURES / n).read_bytes()).hexdigest()
              for n in ("origenes_muestra.csv", "predicciones_muestra.csv")}
    return Prepared(configuration("v2"), origins(), predictions(), series, hashes,
                    procedencia["fuentes"]["meteo_socio_epi_piura_2017_2025_h2_gold.csv"], None, None)


def load_batch():
    """``LoadBatch`` of the 6 districts, as load_data prepares it (GX is not rerun on the subset)."""
    import pandas as pd

    from denguekay.config.paths import DISTRICT_COORDS, UBIGEO_CATALOG
    from denguekay.data.processing.epi_sala import load_ubigeo_catalog
    from denguekay.serving.load_data import prepare_from_tables

    silver = read("panel_muestra.csv")
    hashes = {n: hashlib.sha256((FIXTURES / n).read_bytes()).hexdigest()
              for n in ("panel_muestra.csv", "cobertura_muestra.csv", "etiquetas_muestra.csv", "sala_muestra.csv")}
    return prepare_from_tables(load_ubigeo_catalog(UBIGEO_CATALOG), pd.read_csv(DISTRICT_COORDS), silver,
                               read("cobertura_muestra.csv"), read("etiquetas_muestra.csv"), read("sala_muestra.csv"),
                               hashes, {"exito": True, "suites": [], "nota": "subconjunto de fixtures de la v2"})


def build_sample(cutoff=SERVICE_CUTOFF, trained=None, horizons=(2, 3, 4)):
    from denguekay.serving.predictors import v2_e3_s4 as v2

    return v2.build(sample_prepared(), horizons, options(), pd_date(cutoff), trained=trained)


def pd_date(value):
    import pandas as pd

    return pd.Timestamp(value).date()


def publish_v2(engine, storage, built, *, select=True, run_inference=False, run_id="run-v2", fingerprint="huella-v2"):
    """Load the 6 districts (if not loaded) and publish a v2 package, setting its experimental selection."""
    from denguekay.db.session import transaction
    from denguekay.serving.load_data import persist_load
    from denguekay.serving.publish import publish_to_db

    data = load_batch()
    with transaction(engine) as session:
        persist_load(session, data)
    return publish_to_db(engine, data, built, run_id, fingerprint, storage, 0, servir_no_validadas=True,
                         run_inference=run_inference, select_experimental=select)


def environment_key():
    import xgboost

    from denguekay.model.device import xgboost_settings

    setup = xgboost_settings()
    return {"sistema": platform.system(), "maquina": platform.machine(), "xgboost": xgboost.__version__,
            "configuracion": f"device={setup['device']},n_jobs={setup['n_jobs']}"}


def recording_environment():
    return json.loads(ENVIRONMENT.read_text(encoding="utf-8"))


def same_environment():
    import xgboost

    recorded = recording_environment()
    return (platform.system(), platform.machine(), xgboost.__version__) == (
        recorded["sistema"], recorded["maquina"], recorded["xgboost"])


def skip_reason():
    import xgboost

    recorded = recording_environment()
    return (f"La paridad con reentrenamiento solo es bit a bit en el entorno de grabación "
            f"({recorded['sistema']} {recorded['maquina']}, xgboost {recorded['xgboost']}, {recorded['configuracion']}) "
            f"y con data/ local; aquí: {platform.system()} {platform.machine()}, xgboost {xgboost.__version__}. "
            f"La paridad de variables y la del serving con el modelo congelado sí corren")


# --- what the frozen configuration computes on the full data ------------------------------------

# Runs with the code of RECORDING_COMMIT (inside its worktree) or with the current code (refit parity).
# The data paths point to the main checkout's data/ (read only).
_COMPUTE = """
import base64, io, json, platform
from pathlib import Path
import denguekay.config.paths as paths
data = Path(DATA)
paths.SILVER_INTEGRATED = data / "silver" / "integrado" / "meteo_socio_epi_piura_2017_2025.csv"
paths.SILVER_EPI_HISTORICAL = data / "silver" / "epi_piura_semanal.csv"
paths.GOLD = data / "gold"
paths.GOLD_MANIFEST = paths.GOLD / "manifest_fase6.json"
import denguekay
assert denguekay.__file__.startswith(PACKAGE_ROOT), denguekay.__file__
import numpy as np, pandas as pd, xgboost
from sklearn.linear_model import LogisticRegression
from denguekay.data.loading import load_integrated
from denguekay.evaluation import protocol as pa, variants
from denguekay.model import frozen_configs as cf, horizon_strategies as eh, probabilistic_output as sp
from denguekay.model.device import xgboost_settings

panel = load_integrated(paths.SILVER_INTEGRATED)
rule = json.loads(paths.GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
inputs = variants.inputs(panel, rule)
c = cf.CONFIG_2026
origins = cf.origins(panel, inputs, rule, configuration=c)
preds, models = sp.predict_e3(inputs["matrices"], cf.DEPLOYMENT_SEED, c["formulacion"], return_models=True,
                              columns=c["columnas"], origins=origins, hyperparameters=c["hiperparametros"],
                              dispersion=c["dispersion"])
setup = xgboost_settings()
fingerprint = cf.fingerprint(preds, c)
assert fingerprint == cf.REFERENCE_FINGERPRINTS[cf.setup_key(setup)]["V2"], "no es la v2 congelada"
calibrated, _ = pa.calibrate_chronologically(preds)
block, kind, period = BLOCK
_, cutoff = eh._common_cutoffs(inputs["matrices"], kind, period)
model = models[block]
platt, platt_check = {}, {}
for h, by_h in calibrated.groupby("horizonte"):
    onsets = by_h.groupby("bloque").semana_inicio.min()
    rows = by_h[by_h.bloque.eq(block)]
    first = pa.block_cutoff(rows)
    previous = by_h[by_h.bloque.map(onsets).lt(onsets[block])]
    available = previous[(previous.semana_inicio + pd.Timedelta(days=6)).le(first)]
    q = np.clip(available.probabilidad_brote.to_numpy(float), pa.EPS, 1 - pa.EPS)
    lr = LogisticRegression(C=1e6, max_iter=1000).fit(np.log(q / (1 - q)).reshape(-1, 1), available.brote.to_numpy(int))
    a, b = float(lr.coef_[0, 0]), float(lr.intercept_[0])
    q = np.clip(rows.probabilidad_brote.to_numpy(float), pa.EPS, 1 - pa.EPS)
    from scipy.special import expit
    platt[str(int(h))] = [a, b]
    platt_check[str(int(h))] = float(np.abs(expit(np.log(q / (1 - q)) * a + b) - rows.probabilidad_calibrada).max())
keep = set(DISTRICTS)
columns = ["ubigeo", "anio", "semana", "semana_inicio", "origen_cierre", *c["columnas"], *EXTRA,
           *[f"{v}_h{h}" for h in eh.STRATEGY_HORIZONS for v in ("casos_Dengue", "brote", "semana_inicio")]]
sample_origins = origins.loc[origins.ubigeo.isin(keep), columns]
sample_preds = calibrated.loc[calibrated.ubigeo.isin(keep)].drop(columns=["umbral_diagnostico_f1"])
labels = inputs["etiquetas"].loc[inputs["etiquetas"].ubigeo.isin(keep)]

def csv(frame):
    return frame.to_csv(index=False, lineterminator="\\n")

booster = model["regresor"].get_booster()
print(json.dumps({
    "origenes": csv(sample_origins), "predicciones": csv(sample_preds), "etiquetas": csv(labels),
    "booster": base64.b64encode(bytes(booster.save_raw(raw_format="json"))).decode(),
    "alfa": {str(h): float(a) for h, a in zip(eh.STRATEGY_HORIZONS, model["alphas"])}, "platt": platt,
    "platt_max_diferencia_con_calibrate_chronologically": platt_check,
    "corte_bloque": str(cutoff.date()), "huella_v2": fingerprint,
    "entorno": {"sistema": platform.system(), "maquina": platform.machine(), "xgboost": xgboost.__version__,
                "configuracion": f"device={setup['device']},n_jobs={setup['n_jobs']}"}}))
"""


def compute_frozen(package_root, data_dir):
    """Run ``_COMPUTE`` in a fresh process, CPU with 2 threads, with the package found in ``package_root``."""
    sys.path[:0] = [str(ROOT), str(TESTS)]
    import equivalence_support as eq

    package_root = Path(package_root).resolve()
    env = eq.subprocess_env(**eq.CPU_SETUP)
    env["PYTHONPATH"] = os.pathsep.join([str(package_root / "src"), str(package_root / "tests"), str(package_root)])
    code = (f"PACKAGE_ROOT = {str(package_root)!r}\nDATA = {str(Path(data_dir).resolve())!r}\n"
            f"BLOCK = {PARITY_BLOCK!r}\nDISTRICTS = {DISTRICTS!r}\nEXTRA = {ORIGIN_COLUMNS_EXTRA!r}\n" + _COMPUTE)
    process = subprocess.run([sys.executable, "-c", code], cwd=package_root, env=env,
                             capture_output=True, text=True, timeout=3600)
    if process.returncode != 0:
        raise RuntimeError(process.stderr[-4000:])
    return json.loads(process.stdout.strip().splitlines()[-1])


def _write_new(path, content):
    if path.exists():
        raise SystemExit(f"{path.relative_to(ROOT)} ya existe: la línea base no se sobrescribe")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    print("escrito", path.relative_to(ROOT))


def record(worktree):
    """Data extracts (read only) plus what the code of RECORDING_COMMIT computes on the full data; once."""
    import pandas as pd

    from denguekay.config.paths import GOLD, SILVER_INTEGRATED, SILVER_SALA
    from denguekay.data.validation.gx_quality import read_gold

    worktree = Path(worktree).resolve()
    head = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=worktree, capture_output=True,
                          text=True, check=True).stdout.strip()
    if head != RECORDING_COMMIT:
        raise SystemExit(f"El worktree está en {head}; debe estar en {RECORDING_COMMIT}")
    result = compute_frozen(worktree, ROOT / "data")
    keep = set(DISTRICTS)
    coverage_path = SILVER_INTEGRATED.with_suffix(".coverage.csv")
    gold, gold_path = read_gold(GOLD, 2)
    extracts = {
        "panel_muestra.csv": pd.read_csv(SILVER_INTEGRATED, dtype={"ubigeo": "string"}),
        "cobertura_muestra.csv": pd.read_csv(coverage_path, dtype={"ubigeo": "string"}),
        "etiquetas_muestra.csv": gold[["ubigeo", "anio", "semana", "casos_Dengue", "brote", "umbral_brote_casos"]],
        "sala_muestra.csv": pd.read_csv(SILVER_SALA, dtype={"ubigeo": "string"}),
    }
    for name, frame in extracts.items():
        frame = frame.loc[frame.ubigeo.isin(keep)]
        if name == "sala_muestra.csv":
            frame = frame.loc[frame.anio.eq(2025)]
        _write_new(FIXTURES / name, frame.to_csv(index=False, lineterminator="\n"))
    _write_new(FIXTURES / "origenes_muestra.csv", result["origenes"])
    _write_new(FIXTURES / "predicciones_muestra.csv", result["predicciones"])
    _write_new(PACKAGE / "booster.json", base64.b64decode(result["booster"]))
    meta = {"bloque": PARITY_BLOCK[0], "corte_bloque": result["corte_bloque"], "alfa": result["alfa"],
            "platt": result["platt"],
            "platt_max_diferencia_con_calibrate_chronologically": result["platt_max_diferencia_con_calibrate_chronologically"],
            "nota": "Modelo del bloque calendario_2025 de frozen_configs.predict (65 distritos, semilla 17), su α "
                    "dentro de la muestra y el Platt cronológico de ese bloque (coeficientes de LogisticRegression)"}
    _write_new(PACKAGE / "meta.json", json.dumps(meta, indent=1, ensure_ascii=False) + "\n")
    sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (SILVER_INTEGRATED, coverage_path, gold_path, SILVER_SALA)}
    _write_new(FIXTURES / "procedencia.json", json.dumps({
        "fuentes": sources, "distritos": list(DISTRICTS), "regla_distritos": DISTRICT_RULE,
        "commit_modelo": RECORDING_COMMIT, "huella_v2": result["huella_v2"],
        "nota": "Datos agregados públicos (casos por distrito y semana, clima, población); sin datos personales. "
                "Aprobado por Rosa en la fase 4"}, indent=1, ensure_ascii=False) + "\n")
    _write_new(ENVIRONMENT, json.dumps({**result["entorno"], "commit": RECORDING_COMMIT,
                                        "nota": "Entorno en que se grabaron los resultados del modelo; un "
                                                "reentrenamiento solo los reproduce bit a bit con esta clave"},
                                       indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("accion", choices=["record"])
    parser.add_argument("worktree", help="worktree del commit ab8503b")
    record(parser.parse_args().worktree)
