"""Multi-horizon strategies compared in phase 3 of the architecture study.

All of them use the frozen matrices (``base_6`` for the ``log1p(cases)``
regression and ``base_6_poblacion_2017`` for classification), the same time
blocks and the same fixed hyperparameters; only the way learning is organised
across horizons changes:

- **E1, direct per horizon:** one regressor and one classifier per h.
- **E2, pooled direct:** one regressor and one classifier for h in {2,3,4},
  with stacked rows, generic column names and ``h`` as a variable.
- **E3, multi-output (MIMO):** from each origin, one model predicts the vector
  (t+2, t+3, t+4) with ``multi_strategy="multi_output_tree"``.

The matrices of horizons missing in gold are built **in memory** with
``features.construir_gold``; nothing is written to ``data/``. E2 and E3 share a
single model per block for the three horizons, so they train with the labels
closed before the **earliest** first origin (that of h=4).
"""

import numpy as np
import pandas as pd
from xgboost import XGBClassifier, XGBRegressor

from denguekay.features.gold import build_gold
from denguekay.model.train import (
    SENSITIVITY_TEST_YEAR, MIN_OUTBREAK_CASES, BASE_PARAMS, counts_from_log1p,
    prepare_gold, split_calendar_year, split_season,
)
from denguekay.evaluation.compact_validation import SEASONS, compact_variants
from denguekay.data.validation.forecast_contract import KEY

STRATEGY_HORIZONS = (2, 3, 4)
CURVE_HORIZONS = (1, 2, 3, 4, 5, 6)
SEASONAL_LAG = 52
GENERIC = ["hist_lag_a", "hist_lag_b", "hist_media_4", "hist_semanas_pos_4",
             "semana_epi_seno", "semana_epi_coseno"]
POPULATION = "log_poblacion_censo_2017"
OUTPUT = [*KEY, "semana_inicio", "origen_cierre", "horizonte", "bloque", "casos_Dengue",
          "brote", "umbral_brote_casos", "persistencia", "estacional"]
MODELS_PER_STRATEGY = {"E1": 2 * len(STRATEGY_HORIZONS), "E2": 2, "E3": 2}


# ---------------------------------------------------------------------------
# Matrices in memory
# ---------------------------------------------------------------------------

def horizon_matrix(panel: pd.DataFrame, labels: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Modelling matrix of one horizon, built in memory and audited.

    It uses ``construir_gold`` (the same code as gold h=2/h=4) and ``prepare_gold``
    (same start-up exclusions and origin validation). It adds the seasonal naive
    value: the cases of week ``t - 52``, known at the origin.
    """
    gold = build_gold(panel, horizon, labels, min_outbreak_cases=MIN_OUTBREAK_CASES)
    data, _ = prepare_gold(gold, horizon)
    if not data.origen_cierre.lt(data.semana_inicio).all():
        raise ValueError(f"Fuga temporal en la matriz h={horizon}")
    series = panel[KEY + ["semana_inicio", "casos_Dengue"]].copy()
    series["semana_inicio"] = pd.to_datetime(series.semana_inicio)
    series = series.sort_values(["ubigeo", "semana_inicio"])
    series["estacional"] = series.groupby("ubigeo").casos_Dengue.shift(SEASONAL_LAG)
    data = data.merge(series[KEY + ["estacional"]], on=KEY, how="left", validate="one_to_one")
    data["persistencia"] = data[f"casos_lag_{horizon}"]
    data["horizonte"] = horizon
    return data


def model_columns(horizon: int) -> tuple[list[str], list[str]]:
    """Frozen regression and classification columns for one horizon."""
    variants = compact_variants(horizon)
    return variants["base_6"], variants["base_6_poblacion_2017"]


def to_generic(data: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Rename the history columns of a horizon to common names."""
    reg, _ = model_columns(horizon)
    return data.rename(columns=dict(zip(reg, GENERIC)))


def blocks() -> list[tuple[str, str, int]]:
    """Protocol blocks: seasons 2021-2024 and calendar year 2025."""
    return [*((f"temporada_{t}", "temporada", t) for t in SEASONS),
            (f"calendario_{SENSITIVITY_TEST_YEAR}", "calendario", SENSITIVITY_TEST_YEAR)]


def split(data: pd.DataFrame, kind: str, period: int):
    """Time cutoff shared with ``train.py``."""
    if kind == "temporada":
        return split_season(data, period)
    return split_calendar_year(data, period)


def parameters(seed: int, **extra) -> dict:
    """Fixed hyperparameters of the study with the given seed."""
    return {**BASE_PARAMS, "random_state": seed, **extra}


def _output(test_set: pd.DataFrame, block: str, counts, probability) -> pd.DataFrame:
    output = test_set[[c for c in OUTPUT if c != "bloque"]].copy()
    output["bloque"] = block
    output["casos_predichos"] = np.asarray(counts, float)
    output["probabilidad_brote"] = np.asarray(probability, float)
    if not np.isfinite(output[["casos_predichos", "probabilidad_brote"]].to_numpy()).all():
        raise ValueError("Predicciones no finitas")
    return output[OUTPUT + ["casos_predichos", "probabilidad_brote"]]


def _fit(x_reg, x_cls, y_cases, y_outbreak, seed: int, **extra):
    reg = XGBRegressor(objective="reg:squarederror", **parameters(seed, **extra))
    cls = XGBClassifier(objective="binary:logistic", eval_metric="logloss", **parameters(seed, **extra))
    reg.fit(x_reg, np.log1p(np.asarray(y_cases, float)))
    cls.fit(x_cls, np.asarray(y_outbreak, int))
    return reg, cls


# ---------------------------------------------------------------------------
# E1: direct per horizon
# ---------------------------------------------------------------------------

def predict_e1(matrices: dict[int, pd.DataFrame], seed: int,
                horizons: tuple[int, ...] | None = None) -> pd.DataFrame:
    """One regressor and one classifier per horizon and block."""
    parts = []
    for h in horizons or sorted(matrices):
        data = matrices[h]
        col_reg, col_cls = model_columns(h)
        for block, kind, period in blocks():
            train, test, _ = split(data, kind, period)
            reg, cls = _fit(train[col_reg], train[col_cls], train.casos_Dengue, train.brote, seed)
            parts.append(_output(test, block, counts_from_log1p(reg.predict(test[col_reg])),
                                  cls.predict_proba(test[col_cls])[:, 1]))
    return pd.concat(parts, ignore_index=True).assign(estrategia="E1", semilla=seed)


# ---------------------------------------------------------------------------
# E2: pooled direct (stacked rows with h as a variable)
# ---------------------------------------------------------------------------

def _common_cutoffs(matrices: dict[int, pd.DataFrame], kind: str, period: int):
    """Tests per horizon and the earliest cutoff among them."""
    test_sets, cutoffs = {}, []
    for h in STRATEGY_HORIZONS:
        _, test, cutoff = split(matrices[h], kind, period)
        test_sets[h] = test
        cutoffs.append(cutoff)
    return test_sets, min(cutoffs)


def stack_training(matrices: dict[int, pd.DataFrame], cutoff: pd.Timestamp) -> pd.DataFrame:
    """Rows of the three horizons with a label closed at the cutoff, in generic names."""
    parts = []
    for h in STRATEGY_HORIZONS:
        data = matrices[h]
        closed = data[(data.semana_inicio + pd.Timedelta(days=6)).le(cutoff)]
        if not closed.origen_cierre.lt(closed.semana_inicio).all():
            raise ValueError("Fuga temporal en filas apiladas")
        parts.append(to_generic(closed, h))
    stacked = pd.concat(parts, ignore_index=True)
    if stacked.brote.nunique() < 2:
        raise ValueError("Entrenamiento apilado sin dos clases")
    return stacked


def predict_e2(matrices: dict[int, pd.DataFrame], seed: int) -> pd.DataFrame:
    """One regressor and one classifier per block for h=2, 3 and 4 together."""
    col_reg, col_cls = [*GENERIC, "horizonte"], [*GENERIC, POPULATION, "horizonte"]
    parts = []
    for block, kind, period in blocks():
        test_sets, cutoff = _common_cutoffs(matrices, kind, period)
        train = stack_training(matrices, cutoff)
        if train.semana_inicio.max() >= min(t.semana_inicio.min() for t in test_sets.values()):
            raise ValueError("El entrenamiento apilado alcanza semanas de prueba")
        reg, cls = _fit(train[col_reg], train[col_cls], train.casos_Dengue, train.brote, seed)
        for h, test in test_sets.items():
            g = to_generic(test, h)
            parts.append(_output(test, block, counts_from_log1p(reg.predict(g[col_reg])),
                                  cls.predict_proba(g[col_cls])[:, 1]))
    return pd.concat(parts, ignore_index=True).assign(estrategia="E2", semilla=seed)


# ---------------------------------------------------------------------------
# E3: multi-output from the same origin
# ---------------------------------------------------------------------------

def origin_table(matrix_h2: pd.DataFrame) -> pd.DataFrame:
    """One row per origin with the h=2 predictors and targets t+2, t+3 and t+4.

    The h=2 row with target ``t`` has origin ``o = t - 2``; the h=3 and h=4
    targets are the next weeks of the same district.
    """
    data = to_generic(matrix_h2, 2).sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
    if not data.groupby("ubigeo").semana_inicio.diff().dropna().dt.days.eq(7).all():
        raise ValueError("La matriz h=2 tiene semanas faltantes")
    group = data.groupby("ubigeo")
    for step, h in enumerate(STRATEGY_HORIZONS):
        for col in ("casos_Dengue", "brote", "semana_inicio"):
            data[f"{col}_h{h}"] = group[col].shift(-step)
    return data


def predict_e3(matrices: dict[int, pd.DataFrame], seed: int) -> pd.DataFrame:
    """One multi-output model per task and block for the vector (h=2, 3, 4)."""
    origins = origin_table(matrices[2])
    col_reg, col_cls = list(GENERIC), [*GENERIC, POPULATION]
    targets = [f"semana_inicio_h{h}" for h in STRATEGY_HORIZONS]
    extra = {"multi_strategy": "multi_output_tree"}
    parts = []
    for block, kind, period in blocks():
        test_sets, cutoff = _common_cutoffs(matrices, kind, period)
        complete = origins.dropna(subset=targets)
        last = complete[f"semana_inicio_h{STRATEGY_HORIZONS[-1]}"]
        train = complete[(last + pd.Timedelta(days=6)).le(cutoff)]
        if not train.origen_cierre.lt(train.semana_inicio).all() or train.empty:
            raise ValueError("Entrenamiento multi-salida vacío o con fuga")
        y_cases = np.column_stack([train[f"casos_Dengue_h{h}"] for h in STRATEGY_HORIZONS])
        y_outbreak = np.column_stack([train[f"brote_h{h}"] for h in STRATEGY_HORIZONS]).astype(int)
        reg, cls = _fit(train[col_reg], train[col_cls], y_cases, y_outbreak, seed, **extra)
        counts = counts_from_log1p(reg.predict(origins[col_reg]))
        prob = cls.predict_proba(origins[col_cls])
        for step, h in enumerate(STRATEGY_HORIZONS):
            pred = pd.DataFrame({"ubigeo": origins.ubigeo, "semana_inicio": origins[f"semana_inicio_h{h}"],
                                 "origen_cierre_mimo": origins.origen_cierre,
                                 "casos_predichos": counts[:, step], "probabilidad_brote": prob[:, step]})
            test = test_sets[h].merge(pred.dropna(subset=["semana_inicio"]), on=["ubigeo", "semana_inicio"],
                                    how="left", validate="one_to_one")
            if test.casos_predichos.isna().any() or len(test) != len(test_sets[h]):
                raise ValueError(f"Faltan predicciones multi-salida para h={h}")
            if not test.origen_cierre_mimo.eq(test.origen_cierre).all():
                raise ValueError("El origen multi-salida no coincide con el horizonte")
            parts.append(_output(test, block, test.casos_predichos, test.probabilidad_brote))
    return pd.concat(parts, ignore_index=True).assign(estrategia="E3", semilla=seed)


STRATEGIES = {"E1": predict_e1, "E2": predict_e2, "E3": predict_e3}


# ---------------------------------------------------------------------------
# Coherence across horizons
# ---------------------------------------------------------------------------

def horizon_coherence(data: pd.DataFrame, series: pd.DataFrame,
                          alert: str = "alerta_050") -> pd.DataFrame:
    """Alert contradictions between h=4, h=3 and h=2 for the same target week.

    Going from h=k to h=k-1 adds a single new data point: the cases of week
    ``w - k + 1``. An alert change is **explained** if that data point moved in
    the same direction with respect to the previous week (up -> the alert
    appears; down -> it disappears). **Flicker**: the alert changes twice
    (yes-no-yes or no-yes-no) between h=4, h=3 and h=2.
    """
    cases = series[["ubigeo", "semana_inicio", "casos_Dengue"]].copy()
    cases["semana_inicio"] = pd.to_datetime(cases.semana_inicio)
    cases = cases.set_index(["ubigeo", "semana_inicio"]).casos_Dengue
    evaluable = data[data.horizonte.isin(STRATEGY_HORIZONS) & data.probabilidad_calibrada.notna()]
    table = evaluable.pivot_table(
        index=["bloque", "ubigeo", "semana_inicio"], columns="horizonte", values=alert, aggfunc="first")
    table = table.dropna().astype(bool).reset_index()
    rows = []
    for block, g in table.groupby("bloque"):
        changes = np.zeros(len(g), int)
        unexplained = np.zeros(len(g), bool)
        for k in (4, 3):
            new = g.semana_inicio - pd.to_timedelta(7 * (k - 1), unit="D")
            previous = new - pd.Timedelta(days=7)
            delta = (cases.reindex(list(zip(g.ubigeo, new))).to_numpy()
                     - cases.reindex(list(zip(g.ubigeo, previous))).to_numpy())
            before, after = g[k].to_numpy(), g[k - 1].to_numpy()
            appears, disappears = ~before & after, before & ~after
            changes += appears | disappears
            unexplained |= (appears & ~(delta > 0)) | (disappears & ~(delta < 0))
        flicker = (g[4].to_numpy() != g[3].to_numpy()) & (g[3].to_numpy() != g[2].to_numpy())
        rows.append({"bloque": block, "semanas_objetivo": len(g),
                      "con_cambio": float((changes > 0).mean()),
                      "cambio_sin_explicar": float(unexplained.mean()),
                      "parpadeo": float(flicker.mean()),
                      "alerta_h4_que_desaparece_en_h2": float((g[4] & ~g[2]).mean())})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Preregistered decision with tie-break
# ---------------------------------------------------------------------------

def restrict_horizons(evaluation: dict, horizons: tuple[int, ...] = STRATEGY_HORIZONS) -> dict:
    """Copy of a protocol evaluation with only the given horizons."""
    return {k: (v[v.horizonte.isin(horizons)].reset_index(drop=True)
                if isinstance(v, pd.DataFrame) and "horizonte" in v else v)
            for k, v in evaluation.items()}


def decide_against_reference(evaluations: dict[str, dict[int, dict]], candidate: str,
                                reference: str = "E1") -> pd.DataFrame:
    """Apply ``protocolo_arquitectura.decidir`` with seed medians and ranges.

    ``evaluations[strategy][seed]`` is the output of ``protocolo.evaluar``.
    Lead time uses the paired difference of the reference seed and also
    requires the difference of medians across seeds to have the same sign;
    otherwise the improvement or the worsening is cancelled.
    """
    from denguekay.evaluation import protocol as pa

    met = {e: [evaluations[e][s]["metricas"] for s in evaluations[e]] for e in (candidate, reference)}
    ranges = pa.tie_threshold(pa.seed_ranges(met[candidate]), pa.seed_ranges(met[reference]))
    seed = pa.SEEDS[0]
    diff = pa.lead_time_difference(evaluations[candidate][seed]["antelacion"],
                                   evaluations[reference][seed]["antelacion"], "alerta_050")
    medians = {}
    for e in (candidate, reference):
        table = pd.concat([evaluations[e][s]["antelacion_ic"].query(
            "alerta == 'alerta_050' and bloque == 'seleccion_2022_2023'") for s in evaluations[e]])
        medians[e] = table.groupby("horizonte").avisados_2_o_mas.median()
    sign = np.sign(medians[candidate] - medians[reference]).rename("signo_mediana_antelacion")
    diff = diff.merge(sign, left_on="horizonte", right_index=True)
    # If the seed median does not agree, the CI of the reference seed does not count.
    contradicts_rise = diff.signo_mediana_antelacion <= 0
    diff.loc[contradicts_rise, "ic95_inferior"] = np.minimum(diff.loc[contradicts_rise, "ic95_inferior"], 0)
    contradicts_drop = diff.signo_mediana_antelacion >= 0
    diff.loc[contradicts_drop, "ic95_superior"] = np.maximum(diff.loc[contradicts_drop, "ic95_superior"], 0)
    verdict = pa.decide(pa.seed_median(met[candidate]), pa.seed_median(met[reference]),
                           ranges, diff)
    return verdict.assign(candidata=candidate, referencia=reference).merge(
        diff[["horizonte", "diferencia", "ic95_inferior", "ic95_superior", "signo_mediana_antelacion"]]
        .rename(columns=lambda c: c if c == "horizonte" else f"antelacion_{c}"), on="horizonte")


def adoption(verdicts: pd.DataFrame) -> pd.DataFrame:
    """A candidate is adopted if it wins in some horizon and loses in none."""
    rows = []
    for candidate, g in verdicts.groupby("candidata"):
        wins = g.veredicto.eq("gana").any()
        loses = g.veredicto.eq("pierde").any()
        rows.append({"candidata": candidate, "gana_en": ", ".join(f"h={h}" for h in g.horizonte[g.veredicto.eq("gana")]) or None,
                      "pierde_en": ", ".join(f"h={h}" for h in g.horizonte[g.veredicto.eq("pierde")]) or None,
                      "resultado": "adoptable" if wins and not loses else ("descartada" if loses else "empate")})
    return pd.DataFrame(rows)


def coherence_summary(coherences: dict[str, list[pd.DataFrame]]) -> pd.DataFrame:
    """Median and range across seeds of the unexplained changes per strategy and block."""
    rows = []
    for strategy, tables in coherences.items():
        every = pd.concat(tables, ignore_index=True)
        for block, g in every.groupby("bloque"):
            row = {"estrategia": strategy, "bloque": block}
            for col in ("con_cambio", "cambio_sin_explicar", "parpadeo", "alerta_h4_que_desaparece_en_h2"):
                row[col] = float(g[col].median())
                row[f"rango_{col}"] = float(g[col].max() - g[col].min())
            rows.append(row)
    return pd.DataFrame(rows)


def break_tie(tied: list[str], coherence: pd.DataFrame,
               selection_blocks: tuple[str, ...] = ("temporada_2022", "temporada_2023"),
               models: dict | None = None) -> dict:
    """Preregistered tie-break: (a) coherence across horizons; (b) operational simplicity.

    (a) The strategy with fewer unexplained alert changes in **both**
    selection seasons wins, by more than the larger seed range of the two.
    (b) If (a) does not separate them, the one that trains and deploys fewer models wins.
    """
    if len(tied) == 1:
        return {"elegida": tied[0], "criterio": "única no descartada (no hubo desempate)"}
    c = coherence.set_index(["estrategia", "bloque"])
    best = []
    for e in tied:
        dominates_all = all(
            all(c.at[(o, b), "cambio_sin_explicar"] - c.at[(e, b), "cambio_sin_explicar"]
                > max(c.at[(o, b), "rango_cambio_sin_explicar"], c.at[(e, b), "rango_cambio_sin_explicar"])
                for b in selection_blocks)
            for o in tied if o != e)
        if dominates_all:
            best.append(e)
    if len(best) == 1:
        return {"elegida": best[0], "criterio": "coherencia entre horizontes"}
    models = models or MODELS_PER_STRATEGY
    fewer = min(models[e] for e in tied)
    simple = [e for e in tied if models[e] == fewer]
    return {"elegida": simple[0] if len(simple) == 1 else simple,
            "criterio": "simplicidad operativa" if len(simple) == 1 else "empate sin resolver por simplicidad"}


# ---------------------------------------------------------------------------
# MLflow logging (horizons -> variants -> folds shape)
# ---------------------------------------------------------------------------

BLOCK_TYPE = {"temporada_2021": "calibracion", "temporada_2022": "seleccion",
               "temporada_2023": "seleccion", "temporada_2024": "contraste",
               "calendario_2025": "sensibilidad"}


def mlflow_fold(row: pd.Series, variant: str) -> dict:
    """Turn a ``protocolo.metricas_por_bloque`` row into a loggable fold."""
    value = lambda c: None if c not in row or pd.isna(row[c]) else float(row[c])
    return {
        "horizonte": int(row.horizonte), "variante": variant, "bloque": row.bloque,
        "tipo": BLOCK_TYPE.get(row.bloque, "otro"), "n_prueba": int(row.n),
        "regresion": {"conteos": {"mae": value("mae"), "rmse": value("rmse"), "razon_mae": value("razon_mae"),
                                  "razon_rmse": value("razon_rmse")},
                      "alerta_derivada": {"f1": value("f1_regresion")}},
        "clasificacion": {"alerta_directa": {k: value(f"{k}_050") for k in ("precision", "recall", "f1")}
                          | {"auprc": value("auprc")}, "brier": value("brier")},
        "persistencia": {"conteos": {"mae": value("mae_persistencia"), "rmse": value("rmse_persistencia")},
                         "alerta_derivada": {"f1": value("f1_persistencia"), "auprc": value("auprc_persistencia")}},
    }


def mlflow_report(experiment: str, metrics: dict[str, pd.DataFrame], seeds: tuple[int, ...]) -> dict:
    """Report with the standard shape built from metrics per variant."""
    report = {"experimento": experiment, "semillas": list(seeds),
               "parametros": {k: v for k, v in BASE_PARAMS.items() if k != "random_state"},
               "horizontes": {}}
    for variant, table in metrics.items():
        for h, g in table.groupby("horizonte"):
            block_h = report["horizontes"].setdefault(str(int(h)), {"variantes": {}})
            block_h["variantes"][variant] = {"folds": [mlflow_fold(f, variant) for _, f in g.iterrows()]}
    return report


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def skill_curve_figure(metrics: pd.DataFrame):
    """F1, AUPRC and relative MAE against h, per selection season."""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    for block, g in metrics.groupby("bloque"):
        g = g.sort_values("horizonte")
        label = block.replace("temporada_", "")
        axes[0].plot(g.horizonte, g.f1_050, marker="o", label=f"XGBoost {label}")
        axes[0].plot(g.horizonte, g.f1_persistencia, marker="x", linestyle="--", label=f"Persistencia {label}")
        axes[0].plot(g.horizonte, g.f1_estacional, marker="s", linestyle=":", label=f"Estacional {label}")
        axes[1].plot(g.horizonte, g.auprc, marker="o", label=f"XGBoost {label}")
        axes[1].plot(g.horizonte, g.auprc_persistencia, marker="x", linestyle="--", label=f"Persistencia {label}")
        axes[2].plot(g.horizonte, g.razon_mae, marker="o", label=f"XGBoost {label}")
        axes[2].plot(g.horizonte, g.razon_mae_estacional, marker="s", linestyle=":", label=f"Estacional {label}")
    axes[2].axhline(1, color="grey", linewidth=0.8)
    axes[2].axhline(0.85, color="black", linewidth=0.8, linestyle="--")
    for ax, title in zip(axes, ("F1 de alerta (p ≥ 0,50 calibrada; reglas de casos)",
                                 "AUPRC", "MAE relativo a la persistencia")):
        ax.set_xlabel("Horizonte h (semanas)")
        ax.set_title(title)
        ax.legend(fontsize=7)
    fig.tight_layout()
    return fig
