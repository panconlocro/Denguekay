"""Feature engineering and hyperparameter study on E3·S4_s2 (workflow wrapper).

The architecture and the protocol stay fixed (``salida_probabilistica.predecir_e3``
with ``S4_s2`` and ``protocolo_arquitectura.evaluar``). This module only
orchestrates:

- inputs in memory (panel, labels, series and h=2, 3, 4 matrices), as in
  notebook 31;
- evaluation of a variant (columns and hyperparameters) with the 5 seeds;
- summary of a variant: medians, ranges, lead time and recall on new outbreaks;
- check of the reproduction against ``fase5_decision``;
- inventory of the gold h=2 candidates and their S1 background.

The new variables live in their own module (phase 2b) and the hyperparameter
search in ``hiperparametros.py`` (phase 3). Nothing is written to ``data/``.
"""

import hashlib
import json
import time

import numpy as np
import pandas as pd

from denguekay.model import horizon_strategies as eh
from denguekay.evaluation import protocol as pa
from denguekay.model import probabilistic_output as sp
from denguekay.features.model_input_contract import NON_PREDICTORS, predictor_families
from denguekay.model.train import BASE_PARAMS

STRATEGY, FORMULATION = "E3", "S4_s2"
REFERENCE_NAME = "referencia_B"
JOINT_SELECTION_BLOCK = "seleccion_2022_2023"
REPRODUCTION_DECIMALS = 3
S1_ABLATIONS = {"25_espacial": "ablacion_espacial", "26_clima": "ablacion_clima",
                 "27_sociodemografica": "ablacion_sociodemografica",
                 "28_fracciones": "ablacion_fracciones",
                 "29_poblacion_sin_seguro": "ablacion_poblacion_sin_seguro"}


# ---------------------------------------------------------------------------
# Inputs in memory
# ---------------------------------------------------------------------------

def inputs(panel: pd.DataFrame, rule: dict) -> dict:
    """Labels, series and h=2, 3, 4 matrices as in notebook 31 (phase 3 cell)."""
    from denguekay.features.outbreak_label import SeasonalOutbreakConfig
    from denguekay.features.gold import build_labels

    labels = build_labels(panel, SeasonalOutbreakConfig(
        rule["multiplicador"], rule["anios_previos"], rule["minimo_casos"]))
    series = panel[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]].merge(
        labels[["ubigeo", "anio", "semana", "brote"]], on=["ubigeo", "anio", "semana"])
    series["semana_inicio"] = pd.to_datetime(series.semana_inicio)
    matrices = {h: eh.horizon_matrix(panel, labels, h) for h in eh.STRATEGY_HORIZONS}
    return {"etiquetas": labels, "serie": series, "matrices": matrices}


# ---------------------------------------------------------------------------
# Evaluation of a variant
# ---------------------------------------------------------------------------

def evaluate_variant(matrices: dict[int, pd.DataFrame], series: pd.DataFrame, *,
                     columns: list[str] | None = None, origins: pd.DataFrame | None = None,
                     hyperparameters: dict | None = None, prepare_block=None,
                     seeds: tuple[int, ...] = pa.SEEDS, formulation: str = FORMULATION,
                     dispersion: str = "dentro_muestra") -> dict:
    """Predict with E3 (S4_s2 by default) and apply the frozen protocol, once per seed.

    Returns ``{"predicciones": {seed: df}, "evaluaciones": {seed: dict},
    "alfas": df}`` (alpha of each block, horizon and seed).
    """
    calibration = sp.FORMULATIONS[formulation]["calibracion"]
    predictions, evaluations, alphas = {}, {}, []
    for seed in seeds:
        pred = sp.predict_e3(matrices, seed, formulation, columns=columns,
                              origins=origins, hyperparameters=hyperparameters,
                              prepare_block=prepare_block, dispersion=dispersion)
        alphas.append(pred.attrs.pop("alfas", pd.DataFrame()))
        predictions[seed] = pred
        evaluations[seed] = pa.evaluate(pred, series, calibration)
    return {"predicciones": predictions, "evaluaciones": evaluations,
            "alfas": pd.concat(alphas, ignore_index=True)}


def summarize_variant(evaluations: dict[int, dict], series: pd.DataFrame) -> dict:
    """Seed medians and ranges, lead time and recall per kind of outbreak week."""
    metrics = [r["metricas"] for r in evaluations.values()]
    lead_time = pd.concat({s: r["antelacion_ic"].query("alerta == 'alerta_050'")
                            for s, r in evaluations.items()}, names=["semilla"]).reset_index(level=0)
    persistence = next(iter(evaluations.values()))["antelacion_ic"].query("alerta == 'alerta_persistencia'")
    recall = pd.concat({s: sp.recall_by_week_type(r["datos"], series) for s, r in evaluations.items()},
                       names=["semilla"]).reset_index(level=0)
    return {
        "medianas": pa.seed_median(metrics),
        "rangos": pa.seed_ranges(metrics),
        "antelacion": (lead_time.groupby(["horizonte", "bloque"]).avisados_2_o_mas
                       .agg(mediana="median", minimo="min", maximo="max").reset_index()
                       .merge(persistence[["horizonte", "bloque", "episodios", "avisados_2_o_mas"]]
                              .rename(columns={"avisados_2_o_mas": "persistencia"}),
                              on=["horizonte", "bloque"], how="left")),
        "recall_por_tipo": (recall.groupby(["horizonte", "bloque", "tipo"])
                            .agg(semanas=("semanas", "first"), recall_mediana=("recall", "median"),
                                 recall_minimo=("recall", "min"), recall_maximo=("recall", "max"))
                            .reset_index()),
    }


def lead_time_vs_persistence(evaluation: dict) -> pd.DataFrame:
    """Paired model - persistence difference on clean onsets 2022-2023 (one seed)."""
    t = evaluation["antelacion"]
    return pa.lead_time_difference(t, t, "alerta_050", "alerta_persistencia")


# ---------------------------------------------------------------------------
# Reproduction against the architecture study
# ---------------------------------------------------------------------------

def compare_reproduction(medians: pd.DataFrame, reference: list[dict],
                          decimals: int = REPRODUCTION_DECIMALS) -> pd.DataFrame:
    """Compare, metric by metric, the new medians with the saved ones.

    ``reference`` is ``fase5_decision.metricas_mediana_semillas``. One row per
    (horizon, block, metric) with both values, the absolute difference and whether
    they agree when rounded to ``decimals``. Saved metrics without a new
    counterpart (or the other way round) are also reported, as not matching.
    """
    saved = pd.DataFrame(reference).melt(["horizonte", "bloque"], var_name="metrica", value_name="guardada")
    new_row = medians.melt(["horizonte", "bloque"], var_name="metrica", value_name="reproducida")
    join = saved.merge(new_row, on=["horizonte", "bloque", "metrica"], how="outer")
    g, r = join.guardada.astype(float), join.reproducida.astype(float)
    both_null = g.isna() & r.isna()
    join["diferencia_absoluta"] = (g - r).abs()
    join["coincide"] = both_null | (g.round(decimals) == r.round(decimals))
    return join.sort_values(["horizonte", "bloque", "metrica"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Inventory of gold h=2 candidates and S1 background
# ---------------------------------------------------------------------------

def candidate_inventory(gold_h2: pd.DataFrame, matrix_h2: pd.DataFrame) -> pd.DataFrame:
    """Family and start-up nulls of each predictor candidate of gold h=2.

    ``nulos_gold`` counts nulls in the whole gold; ``nulos_tras_arranque`` those
    left in the modelling matrix (after the ``prepare_gold`` exclusions), and
    ``en_base_6`` flags the 6 of the reference.
    """
    family = {c: f for f, cols in predictor_families(2).items() for c in cols}
    candidates = [c for c in gold_h2.columns if c not in NON_PREDICTORS]
    without_family = [c for c in candidates if c not in family]
    if without_family:
        raise ValueError(f"Candidatas de gold sin familia en el contrato: {without_family}")
    base = set(eh.model_columns(2)[0])
    rows = []
    for c in candidates:
        g = gold_h2[c]
        first = gold_h2.loc[g.notna(), "semana_inicio"].min()
        rows.append({"columna": c, "familia": family[c], "en_base_6": c in base,
                      "nulos_gold": int(g.isna().sum()), "fraccion_nulos_gold": float(g.isna().mean()),
                      "primera_semana_con_valor": str(pd.Timestamp(first).date()) if pd.notna(first) else None,
                      "nulos_tras_arranque": int(matrix_h2[c].isna().sum()) if c in matrix_h2 else None})
    return pd.DataFrame(rows)


def _validation_f1(variant: dict, approach: str) -> dict[str, float]:
    """Validation F1 per season of a variant of ablations 25-29."""
    output = {}
    for fold in variant["folds_validacion"]:
        block = fold[approach]
        f1 = (block.get("alerta_derivada", {}) if approach == "regresion" else block.get("alerta_directa", {})).get("f1")
        output[fold["bloque"]] = None if f1 is None else float(f1)
    return output


def s1_background(ablation_metrics: dict[str, dict], horizon: str = "2") -> pd.DataFrame:
    """Result of each variant in ablations 25-29 (S1, its own protocol).

    Per variant: columns added to ``base_6``, mean validation F1 (2021-2023) of
    the alert derived from the regression and of the classifier, its difference
    with ``base_6`` and whether it was chosen in validation. **Background:** a
    different protocol (threshold chosen in validation, mean F1, no seed ranges),
    so it is not comparable with the verdicts of this study.
    """
    rows = []
    for notebook, d in ablation_metrics.items():
        block_h = d["horizontes"][horizon]
        chosen = block_h.get("elegidas_solo_validacion", {})
        flat = {}
        for k, v in chosen.items():
            if isinstance(v, dict):
                for approach, var in v.items():
                    flat.setdefault(var, []).append(f"{k}:{approach}")
            else:
                flat.setdefault(v, []).append(k)
        variants = block_h["variantes"]
        base_cols = set(variants["base_6"]["columnas"])
        base_mean = {e: np.nanmean([x for x in _validation_f1(variants["base_6"], e).values() if x is not None])
                      for e in ("regresion", "clasificacion")}
        for name, var in variants.items():
            row = {"ablacion": notebook, "variante": name,
                    "columnas_agregadas": [c for c in var["columnas"] if c not in base_cols],
                    "elegida_en_validacion": ", ".join(flat.get(name, [])) or None}
            for approach, short in (("regresion", "reg"), ("clasificacion", "cls")):
                f1 = [x for x in _validation_f1(var, approach).values() if x is not None]
                media = float(np.mean(f1)) if f1 else None
                row[f"f1_val_medio_{short}"] = media
                row[f"delta_f1_val_{short}_vs_base_6"] = None if media is None else media - base_mean[approach]
            rows.append(row)
    return pd.DataFrame(rows)


def load_ablations(directory) -> dict[str, dict]:
    """Read the JSON files of ablations 25-29 (read only)."""
    return {n: json.loads((directory / f"{a}.json").read_text(encoding="utf-8"))
            for n, a in S1_ABLATIONS.items()}


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

def time_fit(matrices: dict[int, pd.DataFrame], series: pd.DataFrame, seed: int = 17,
                 repetitions: int = 3, hyperparameters: dict | None = None) -> pd.DataFrame:
    """Seconds of a complete fit (5 blocks x 1 seed) and of its evaluation."""
    rows = []
    for i in range(repetitions):
        t0 = time.perf_counter()
        pred = sp.predict_e3(matrices, seed, FORMULATION, hyperparameters=hyperparameters)
        t1 = time.perf_counter()
        pa.evaluate(pred, series, sp.FORMULATIONS[FORMULATION]["calibracion"])
        t2 = time.perf_counter()
        rows.append({"repeticion": i + 1, "segundos_ajuste_prediccion": t1 - t0,
                      "segundos_evaluacion": t2 - t1, "segundos_total": t2 - t0})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# MLflow (standard horizons -> variants -> folds shape)
# ---------------------------------------------------------------------------

def directory_fingerprint(directory) -> str:
    """Fingerprint of the saved predictions of a phase (every ``*.csv.gz``) and of the protocol."""
    from pathlib import Path

    files = sorted(Path(directory).glob("*.csv.gz"))
    if not files:
        raise FileNotFoundError(f"No hay predicciones en {directory}")
    return predictions_fingerprint(pd.concat([pd.read_csv(f, dtype={"ubigeo": "string"}).assign(archivo=f.name)
                                          for f in files], ignore_index=True))


def predictions_fingerprint(predictions: pd.DataFrame) -> str:
    """Fingerprint of a record: SHA-256 of the predictions and of the protocol version.

    Rows are sorted by key, horizon, block and seed, and columns by name, so the
    concatenation order does not change it. The protocol version is the hash of
    the protocol module's source. It does not depend on the rest of the package:
    rerunning a notebook with identical predictions does not log another run.
    """
    from pathlib import Path

    keys = [c for c in ("archivo", "ubigeo", "anio", "semana", "horizonte", "bloque", "semilla") if c in predictions]
    canonical = predictions.sort_values(keys).reset_index(drop=True)
    canonical = canonical[sorted(canonical.columns)]
    total = hashlib.sha256(canonical.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8"))
    total.update(hashlib.sha256(Path(pa.__file__).read_bytes()).digest())
    return total.hexdigest()


def mlflow_report(experiment: str, medians: dict[str, pd.DataFrame],
                   seeds: tuple[int, ...] = pa.SEEDS, hyperparameters: dict | None = None) -> dict:
    """Report loggable with ``tracking`` for one or several variants."""
    report = eh.mlflow_report(experiment, medians, seeds)
    report["parametros"] = {**{k: v for k, v in BASE_PARAMS.items() if k != "random_state"},
                             "multi_strategy": "multi_output_tree", "objective": "count:poisson",
                             **(hyperparameters or {})}
    report["estrategia"], report["formulacion"] = STRATEGY, FORMULATION
    return report
