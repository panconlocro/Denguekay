"""Closing of V3 (Rosa, 2026-11-09): L + 5a + d3 with the hyperparameters of trial 191 of ``HP_TUNING``.

One run, 5 seeds and every block, of V3 and of its paired comparator without climate (L + 5a with the same
hyperparameters). Each prediction row is saved with what is needed to recompute it: the model's count (mu), the
published count (mixture with the persistence), the NB2 alpha used, the raw and calibrated probabilities, the Platt
parameters of its block and horizon, and the rows and positives the calibrator used. V3 must reproduce
``ajuste_hp/predicciones_candidata.csv.gz`` (G41).

Run: ``python research/06_model_improvement/code/phase_v3_close.py`` (from the repository root).
"""

from __future__ import annotations

import json
import os
import sys
import time

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from denguekay.config.paths import MODELS, ROOT
from denguekay.evaluation import protocol as pa

import phase3_onsets as p3
import phase5_counts as p5
import phase_hp_tuning as ht
import preregistration as pr

# Trial 191 of the HP_TUNING study (models/experimentos/mejora_modelo/ajuste_hp/optuna.db), adopted by Rosa on
# 2026-11-09. Exact values as Optuna stored them.
HP_191 = {"max_depth": 8, "min_child_weight": 1.3472042263917448, "learning_rate": 0.012202198485831055,
          "n_estimators": 1055, "subsample": 0.6374222616667551, "colsample_bytree": 0.5231175260584356,
          "reg_lambda": 27.462610520474446, "reg_alpha": 0.8263569818396628, "gamma": 0.010338285504760625,
          "max_delta_step": 1.5830208659380955}

OUT = MODELS / "experimentos" / "mejora_modelo" / "v3"
FILES = {"V3": "predicciones_v3.csv.gz", "L + 5a": "predicciones_l5a_sin_clima.csv.gz"}
SAVED_CANDIDATE = MODELS / "experimentos" / "mejora_modelo" / "ajuste_hp" / "predicciones_candidata.csv.gz"
KEY = ["ubigeo", "semana_inicio", "horizonte", "bloque"]
TABLE_COLUMNS = ["variante", "semilla", "bloque", "horizonte", "ubigeo", "anio", "semana", "semana_inicio",
                 "origen_cierre", "casos_Dengue", "brote", "umbral_brote_casos", "persistencia", "estacional",
                 "mu_modelo", "w_mezcla", "conteo_publicado", "alpha_usada", "probabilidad_cruda",
                 "probabilidad_calibrada", "platt_a", "platt_b", "filas_calibracion", "positivos_calibracion"]


def hyperparameters() -> dict:
    """The V3 hyperparameters: the inherited ones replaced by trial 191 (all ten are tuned)."""
    return {**ht.inherited(), **HP_191}


def variant_columns() -> dict[str, list[str]]:
    base, _ = p3._config()
    return {"V3": ht.study_columns(), "L + 5a": list(base)}


def platt_parameters(pred: pd.DataFrame) -> pd.DataFrame:
    """Platt slope (``platt_a``) and intercept (``platt_b``) per horizon and block, fitted exactly as
    ``protocol.calibrate_chronologically`` does (earlier blocks whose label closed by the block's first origin).
    Calibrated p = 1 / (1 + exp(-(platt_a · logit(clip(p)) + platt_b))). Blocks without two classes: NaN."""
    data = pa.validate_predictions(pred)
    rows = []
    for h, by_h in data.groupby("horizonte"):
        onsets = by_h.groupby("bloque").semana_inicio.min().sort_values()
        for block, start in onsets.items():
            cutoff = pa.block_cutoff(by_h[by_h.bloque.eq(block)])
            previous = by_h[by_h.bloque.map(onsets).lt(start)]
            available = previous[(previous.semana_inicio + pd.Timedelta(days=6)).le(cutoff)]
            row = {"horizonte": h, "bloque": block, "filas_calibracion": len(available),
                   "positivos_calibracion": int(available.brote.sum()), "platt_a": np.nan, "platt_b": np.nan}
            if available.brote.nunique() == 2:
                model = pa.fit_platt(available.probabilidad_brote, available.brote)
                row.update(platt_a=float(model.coef_[0, 0]), platt_b=float(model.intercept_[0]))
            rows.append(row)
    return pd.DataFrame(rows)


def apply_platt(p, a, b) -> np.ndarray:
    z = np.asarray(a, float) * pa.platt_logit(p) + np.asarray(b, float)
    return 1.0 / (1.0 + np.exp(-z))


def full_table(pred: pd.DataFrame, fits: pd.DataFrame, variant: str, seed: int) -> pd.DataFrame:
    """Every saved column of one seed's predictions (see TABLE_COLUMNS and docs/modeling/protocolo_v3.md)."""
    base = pred.assign(semana_inicio=pd.to_datetime(pred.semana_inicio), origen_cierre=pd.to_datetime(pred.origen_cierre))
    mixed, w = p5.mix_chronologically(base)
    calibrated, _ = pa.calibrate_chronologically(base)
    out = base.rename(columns={"casos_predichos": "mu_modelo", "probabilidad_brote": "probabilidad_cruda"})
    out["conteo_publicado"] = mixed.casos_predichos.to_numpy(float)
    cal = calibrated.assign(ubigeo=calibrated.ubigeo.astype(object))[KEY + ["probabilidad_calibrada"]]
    out = out.merge(cal, on=KEY, how="left", validate="one_to_one")
    out = out.merge(w[["horizonte", "bloque", "w"]].rename(columns={"w": "w_mezcla"}), on=["horizonte", "bloque"],
                    how="left", validate="many_to_one")
    f = fits[fits.semilla.eq(seed)]
    if f.regimen.notna().any() or f.bloque.duplicated().any():
        raise ValueError("Se esperaba un solo ajuste (sin regímenes) por bloque")
    alpha = f.melt(id_vars="bloque", value_vars=[f"alpha_h{h}" for h in p3.H], var_name="horizonte",
                   value_name="alpha_usada")
    alpha["horizonte"] = alpha.horizonte.str[len("alpha_h"):].astype(int)
    out = out.merge(alpha, on=["bloque", "horizonte"], how="left", validate="many_to_one")
    out = out.merge(platt_parameters(base), on=["horizonte", "bloque"], how="left", validate="many_to_one")
    out = out.assign(variante=variant, semilla=seed)
    return out[TABLE_COLUMNS]


def check_table(table: pd.DataFrame) -> dict:
    """The saved parameters reproduce the saved values: Platt -> calibrated p, w -> published count."""
    has = table.platt_a.notna()
    p = apply_platt(table.probabilidad_cruda[has], table.platt_a[has], table.platt_b[has])
    count = table.w_mezcla * table.mu_modelo + (1 - table.w_mezcla) * table.persistencia
    return {"platt_diferencia_maxima": float(np.abs(p - table.probabilidad_calibrada[has]).max()),
            "calibrada_sin_platt": int((table.probabilidad_calibrada.notna() & ~has).sum()),
            "conteo_diferencia_maxima": float(np.abs(count - table.conteo_publicado).max()),
            "alpha_nulos": int(table.alpha_usada.isna().sum())}


def block_metrics(table: pd.DataFrame) -> pd.DataFrame:
    """Brier and AUPRC of the calibrated probability per variant, seed, horizon and block (blocks with Platt)."""
    rows = []
    for (v, s, h, b), g in table.groupby(["variante", "semilla", "horizonte", "bloque"]):
        if g.probabilidad_calibrada.isna().any():
            continue
        y, pc = g.brote.to_numpy(int), g.probabilidad_calibrada.to_numpy(float)
        rows.append({"variante": v, "semilla": int(s), "horizonte": int(h), "bloque": b, "n": len(g),
                     "positivos": int(y.sum()), "brier": float(np.mean((pc - y) ** 2)),
                     "auprc": float(average_precision_score(y, pc)) if y.any() else None})
    return pd.DataFrame(rows)


def read_table(path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"ubigeo": "string"}, float_precision="round_trip").assign(
        ubigeo=lambda d: d.ubigeo.astype(object))


def raw_predictions(table: pd.DataFrame, seed: int) -> pd.DataFrame:
    """The seed's predictions in the protocol format (for G41 and the fingerprint)."""
    t = table[table.semilla.eq(seed)]
    return t.rename(columns={"mu_modelo": "casos_predichos", "probabilidad_cruda": "probabilidad_brote"})[
        ["ubigeo", "semana_inicio", "horizonte", "bloque", "casos_predichos", "probabilidad_brote"]].reset_index(drop=True)


class FileLog:
    """Paths under the repository opened while it is active (audit hook), to list the data V3 needs."""

    def __init__(self):
        self.paths: set[str] = set()
        self.active = False
        root = os.path.normcase(str(ROOT))

        def hook(event, args):
            if not (self.active and event == "open" and args) or isinstance(args[0], int):
                return
            path = args[0]
            path = os.path.normcase(os.path.abspath(path.decode() if isinstance(path, bytes) else str(path)))
            if path.startswith(root) and ".venv" not in path:
                self.paths.add(os.path.relpath(path, root))
        sys.addaudithook(hook)


def run(seeds=pr.SEEDS) -> dict:
    import phase_2026 as p26

    log = FileLog()
    log.active = True
    OUT.mkdir(parents=True, exist_ok=True)
    timings = {}
    start = time.perf_counter()
    inp = p26.inputs_2026()
    origins, _ = p26.add_climate(inp)
    timings["entradas_s"] = time.perf_counter() - start
    hp = hyperparameters()
    result = {"hiperparametros": hp, "semillas": list(seeds)}
    for variant, columns in variant_columns().items():
        start = time.perf_counter()
        res = p26.run_variant(inp, origins, columns, hp, seeds)
        tables = [full_table(res["predicciones"][s], res["ajustes"], variant, s) for s in seeds]
        table = pd.concat(tables, ignore_index=True)
        table.to_csv(OUT / FILES[variant], index=False)
        timings[f"{variant}_s"] = time.perf_counter() - start
        protocol = pa.seed_median([e["metricas"] for e in res["evaluaciones"].values()])
        mine = block_metrics(table).groupby(["horizonte", "bloque"])[["brier", "auprc"]].median().reset_index()
        both = mine.merge(protocol[["horizonte", "bloque", "brier", "auprc"]], on=["horizonte", "bloque"],
                          suffixes=("", "_protocolo"))
        result[variant] = {"filas": len(table), "columnas": list(table.columns), "comprobaciones": check_table(table),
                           "igual_al_protocolo": {c: float(np.abs(both[c] - both[f"{c}_protocolo"]).max())
                                                  for c in ("brier", "auprc")}}
        if variant == "V3":
            saved = p26.read_saved(SAVED_CANDIDATE)
            result["G41_V3"] = p26.guard_old_blocks({s: raw_predictions(read_table(OUT / FILES[variant]), s)
                                                     for s in seeds}, saved)
    log.active = False
    result["tiempos_s"] = timings
    result["archivos_leidos"] = sorted(log.paths)
    return result




# --- Outputs for the registry and the paper (no retraining) ---------------------------------------------------

def cutoff_table(inp: dict, origins: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """Per block and horizon (R20): training cutoff and rows, origin and target ranges, Platt blocks, calibration
    rows and positives. ``table`` is one variant and one seed (the cutoffs do not depend on the seed)."""
    from denguekay.model import horizon_strategies as eh
    import phase_2026 as p26

    data = table.assign(semana_inicio=pd.to_datetime(table.semana_inicio), origen_cierre=pd.to_datetime(table.origen_cierre))
    rows = []
    for block, kind, period in p26.blocks():
        _, cutoff = eh._common_cutoffs(inp["matrices"], kind, period)
        train = p3._training(origins, cutoff)
        for h in p3.H:
            g = data[data.bloque.eq(block) & data.horizonte.eq(h)]
            by_h = data[data.horizonte.eq(h)]
            onsets = by_h.groupby("bloque").semana_inicio.min()
            first = pa.block_cutoff(g)
            prev = by_h[by_h.bloque.map(onsets).lt(onsets[block])]
            used = prev[(prev.semana_inicio + pd.Timedelta(days=6)).le(first)]
            rows.append({
                "bloque": block, "horizonte": h, "corte_entrenamiento": cutoff.date(),
                "filas_entrenamiento": len(train), "primer_origen_entrenamiento": train.origen_cierre.min().date(),
                "ultimo_origen_entrenamiento": train.origen_cierre.max().date(),
                "ultima_semana_objetivo_h4_entrenamiento": pd.Timestamp(train[f"semana_inicio_h{p3.H[-1]}"].max()).date(),
                "primer_origen": g.origen_cierre.min().date(), "ultimo_origen": g.origen_cierre.max().date(),
                "primera_semana_objetivo": g.semana_inicio.min().date(), "ultima_semana_objetivo": g.semana_inicio.max().date(),
                "filas_evaluacion": len(g), "positivos_evaluacion": int(g.brote.sum()),
                "bloques_platt": ", ".join(sorted(used.bloque.unique(), key=lambda b: onsets[b])),
                "filas_calibracion": len(used), "positivos_calibracion": int(used.brote.sum()),
                "ultima_etiqueta_calibracion": (used.semana_inicio.max() + pd.Timedelta(days=6)).date() if len(used) else None})
    return pd.DataFrame(rows)


def summarize(out_json) -> dict:
    """Fingerprint, per-block metrics, cutoff table and the run record, written to ``out_json``."""
    from denguekay.model import device
    from denguekay.model import frozen_configs as fc
    import phase_2026 as p26

    run_record = json.loads((OUT / "corrida_v3.json").read_text(encoding="utf-8"))
    tables = {v: read_table(OUT / f) for v, f in FILES.items()}
    v3 = tables["V3"]
    inp = p26.inputs_2026()
    origins, _ = p26.add_climate(inp)
    cuts = cutoff_table(inp, origins, v3[v3.semilla.eq(fc.DEPLOYMENT_SEED)])
    check = tables["V3"][tables["V3"].semilla.eq(17)].merge(
        cuts[["bloque", "horizonte", "filas_calibracion", "positivos_calibracion"]], on=["bloque", "horizonte"],
        suffixes=("", "_corte"))
    if not (check.filas_calibracion.eq(check.filas_calibracion_corte).all()
            and check.positivos_calibracion.eq(check.positivos_calibracion_corte).all()):
        raise ValueError("La tabla de cortes no coincide con las filas de calibración guardadas")
    metrics = pd.concat([block_metrics(t) for t in tables.values()], ignore_index=True)
    setup = device.xgboost_settings()
    fingerprint = fc.fingerprint(raw_predictions(v3, fc.DEPLOYMENT_SEED), fc.CONFIG_V3)

    def records(df):
        return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False, double_precision=15))

    out = {"huella": {"definicion": fc.FINGERPRINT_DEFINITION, "semilla": fc.DEPLOYMENT_SEED,
                      "entorno": fc.setup_key(setup), "sha256": fingerprint},
           "corrida": {k: run_record[k] for k in ("G41_V3", "tiempos_s", "semillas")},
           "comprobaciones": {v: run_record[v]["comprobaciones"] for v in FILES},
           "archivos_leidos": run_record["archivos_leidos"],
           "cortes": records(cuts), "metricas_por_bloque": metrics.to_dict(orient="records")}
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return out


# --- Release bundles (Rosa, 2026-11-09) ------------------------------------------------------------------------

EXPERIMENTS = MODELS / "experimentos" / "mejora_modelo"
COMPARATOR_FILES = [
    *(EXPERIMENTS / "fase6" / f"{kind}_{name}.csv{ext}"
      for name in ("6a_prima_poisson_glm", "6a_nb_glm", "6b_lightgbm")
      for kind, ext in (("predicciones", ".gz"), ("ajustes", ""))),
    *sorted((EXPERIMENTS / "matriz_clima").glob("*.csv.gz")),
    *sorted((EXPERIMENTS / "temporada_2026").glob("predicciones_*.csv.gz")),
    *sorted((EXPERIMENTS / "temporada_2026").glob("fuera_de_temporada_*.csv.gz")),
]


def build_release(folder, repository: str = "panconlocro/Denguekay") -> dict:
    """The three zips of the model/v3 Release in ``folder`` (outside the repository) and their manifest.

    ``datos_v3.zip``: every file under ``data/`` (and the CHIRPS preliminary daily input under
    ``models/experimentos/``) that the closing run opened (``corrida_v3.json → archivos_leidos``).
    ``predicciones_v3.zip``: the closing run's predictions and record. ``comparadores_v3.zip``: saved
    predictions of the other variants (``COMPARATOR_FILES``)."""
    from pathlib import Path

    from denguekay.data.ingestion import release_bundles as rb

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    read = json.loads((OUT / "corrida_v3.json").read_text(encoding="utf-8"))["archivos_leidos"]
    data_files = [ROOT / p for p in read if p.startswith("data") or "chirps_prelim" in p]
    prediction_files = [OUT / f for f in (*FILES.values(), "corrida_v3.json")]
    bundles = [("datos_v3.zip", data_files, ["data", "models/experimentos"]),
               ("predicciones_v3.zip", prediction_files, "models/experimentos"),
               ("comparadores_v3.zip", COMPARATOR_FILES, "models/experimentos")]
    entries = []
    for name, files, prefix in bundles:
        missing = [str(f) for f in files if not f.exists()]
        if missing:
            raise FileNotFoundError(missing)
        start = time.perf_counter()
        entry = rb.build_bundle(files, folder / name, prefix)
        entry["segundos_armado"] = round(time.perf_counter() - start, 1)
        entries.append(entry)
    return {"version": "v3", "tag": "model/v3", "repositorio": repository, "fecha": "2026-11-09",
            "descripcion": "Paquetes del Release de model/v3: entradas de datos para reentrenar la V3, sus "
                           "predicciones de referencia y las de los comparadores. Se descargan y verifican con "
                           "python -m denguekay.data.ingestion.release_bundles",
            "paquetes": entries}


# --- Verification from a clone (docs/modeling/reproducir_v3.md) -------------------------------------------------

METRICS_JSON = ROOT / "research" / "06_model_improvement" / "docs" / "metricas" / "v3.json"


def verify_metrics(tol: float = 1e-12) -> dict:
    """Brier and AUPRC recomputed from the saved predictions equal ``docs/metricas/v3.json`` (no retraining)."""
    tables = pd.concat([read_table(OUT / f) for f in FILES.values()], ignore_index=True)
    new = block_metrics(tables)
    saved = pd.DataFrame(json.loads(METRICS_JSON.read_text(encoding="utf-8"))["metricas_por_bloque"])
    key = ["variante", "semilla", "horizonte", "bloque"]
    m = new.merge(saved, on=key, how="outer", suffixes=("", "_json"), indicator=True)
    both = m[m._merge.eq("both")]
    diff = {c: float(np.nanmax(np.abs(both[c].astype(float) - both[f"{c}_json"].astype(float)))) for c in ("brier", "auprc")}
    return {"celdas": len(both), "sin_par": int((~m._merge.eq("both")).sum()), "diferencia_maxima": diff,
            "tolerancia": tol, "pasa": bool(m._merge.eq("both").all() and all(v <= tol for v in diff.values()))}


def verify_retrain(seed: int = 17) -> dict:
    """Retrain V3 with one seed on every block; G41 against the saved predictions of that seed and, for seed 17,
    the behavioural fingerprint against ``frozen_configs.V3_FINGERPRINTS`` for this device."""
    import phase_2026 as p26
    from denguekay.model import device
    from denguekay.model import frozen_configs as fc

    start = time.perf_counter()
    inp = p26.inputs_2026()
    origins, _ = p26.add_climate(inp)
    pred = p26.run_variant(inp, origins, variant_columns()["V3"], hyperparameters(), seeds=[seed])["predicciones"][seed]
    seconds = time.perf_counter() - start
    saved = raw_predictions(read_table(OUT / FILES["V3"]), seed)
    guard = p26.guard_old_blocks({seed: pred}, {seed: saved})
    setup = fc.setup_key(device.xgboost_settings())
    out = {"semilla": seed, "entorno": setup, "segundos": round(seconds, 1), "G41": guard}
    if seed == fc.DEPLOYMENT_SEED:
        mine = fc.fingerprint(pred, fc.CONFIG_V3)
        expected = fc.V3_FINGERPRINTS.get(setup)
        out["huella"] = {"calculada": mine, "esperada": expected,
                         "coincide": None if expected is None else mine == expected}
    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Cierre de la V3 (estudio 06) y su verificación desde un clon.")
    parser.add_argument("accion", nargs="?", default="cierre", choices=["cierre", "verificar", "metricas"],
                        help="cierre: corrida de 5 semillas (escribe en models/experimentos); verificar: reentrena "
                             "una semilla y compara; metricas: solo recalcula Brier y AUPRC desde las predicciones")
    parser.add_argument("--semilla", type=int, default=17)
    args = parser.parse_args()
    if args.accion == "cierre":
        out = run()
        (OUT / "corrida_v3.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print("G41:", out["G41_V3"]["pasa"], out["G41_V3"]["diferencia_maxima"], "| tiempos:", out["tiempos_s"], flush=True)
    else:
        result = {"metricas": verify_metrics()}
        if args.accion == "verificar":
            result["reentrenamiento"] = verify_retrain(args.semilla)
        print(json.dumps(result, ensure_ascii=False, indent=1, default=str), flush=True)
        ok = result["metricas"]["pasa"] and result.get("reentrenamiento", {}).get("G41", {}).get("pasa", True)
        print("VERIFICACION:", "PASA" if ok else "NO PASA", flush=True)
        sys.exit(0 if ok else 1)
