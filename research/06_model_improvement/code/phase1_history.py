"""Phase 1a of the model improvement study: the V1 matrix trained from 2005.

Everything is built in memory from the long case series of phase 0 (silver
epi 2000-2016 with absences as zero, the integrated panel from 2017) and the
gold outbreak rule extended with ``future_outbreak_threshold``. Only cases and
calendar enter (``base_6`` + B3), so no climate or socio data before 2017 is
needed. Nothing is written to ``data/``.

``predict_blocks`` repeats, block by block, the non-OOS path of
``probabilistic_output.predict_e3`` with an arbitrary list of seasonal blocks;
with the V1 origins and the 2021-2025 blocks it must reproduce the saved V1
predictions (guard G2).
"""

import numpy as np
import pandas as pd

from denguekay.data.seasons import assign_season
from denguekay.data.validation.forecast_contract import KEY
from denguekay.features import onset_features as fi
from denguekay.features.history_calendar import build_history_calendar
from denguekay.model import horizon_strategies as eh
from denguekay.model import probabilistic_output as sp
from denguekay.model.train import SEASON_START_WEEK, SENSITIVITY_TEST_YEAR

FIRST_BLOCK_SEASON_LONG = 2008       # L: blocks 2008-2024 (+ calendar 2025); 2008 only calibrates
FIRST_BLOCK_SEASON_2017 = 2018       # R: blocks 2018-2024 (+ calendar 2025); 2018 only calibrates
LAST_SEASON = 2024
B3 = fi.COLUMNS["B3"]
V1_COLUMNS = [*eh.GENERIC, *B3]


def seasonal_blocks(first_season: int, last_season: int = LAST_SEASON) -> list[tuple[str, str, int]]:
    """Blocks of the new protocol: one per season and the 2025 calendar year (count sensitivity)."""
    return [*((f"temporada_{t}", "temporada", t) for t in range(first_season, last_season + 1)),
            (f"calendario_{SENSITIVITY_TEST_YEAR}", "calendario", SENSITIVITY_TEST_YEAR)]


# ---------------------------------------------------------------------------
# Long matrices and origins
# ---------------------------------------------------------------------------

def long_matrix(cases: pd.DataFrame, labels: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Matrix of one horizon from ``cases`` (2000-2025) with the rows that have a label and a full ``base_6``.

    Same columns and conventions as ``eh.horizon_matrix`` (``persistencia``,
    ``estacional``, ``temporada``) for the history and calendar family.
    """
    hist = build_history_calendar(cases, horizon)
    data = hist.merge(cases[KEY + ["casos_Dengue"]], on=KEY, validate="one_to_one")
    data = data.merge(labels[KEY + ["umbral_brote_casos", "brote"]], on=KEY, how="inner", validate="one_to_one")
    base = eh.model_columns(horizon)[0]
    data = data.dropna(subset=base).copy()
    data["semana_inicio"] = pd.to_datetime(data.semana_inicio)
    if not data.origen_cierre.lt(data.semana_inicio).all():
        raise ValueError(f"Fuga temporal en la matriz larga h={horizon}")
    series = cases[KEY + ["semana_inicio", "casos_Dengue"]].copy()
    series["semana_inicio"] = pd.to_datetime(series.semana_inicio)
    series = series.sort_values(["ubigeo", "semana_inicio"])
    series["estacional"] = series.groupby("ubigeo").casos_Dengue.shift(eh.SEASONAL_LAG)
    data = data.merge(series[KEY + ["estacional"]], on=KEY, how="left", validate="one_to_one")
    data["persistencia"] = data[f"casos_lag_{horizon}"]
    data["horizonte"] = horizon
    data["temporada"] = assign_season(data.anio, data.semana, SEASON_START_WEEK)
    return data.sort_values(["semana_inicio", "ubigeo"]).reset_index(drop=True)


def long_matrices(cases: pd.DataFrame, labels: pd.DataFrame) -> dict[int, pd.DataFrame]:
    return {h: long_matrix(cases, labels, h) for h in eh.STRATEGY_HORIZONS}


def long_origins(cases: pd.DataFrame, matrix_h2: pd.DataFrame) -> pd.DataFrame:
    """Origin table (``eh.origin_table``) with B3 computed on the whole long series."""
    origins = eh.origin_table(matrix_h2)
    no_history = cases.iloc[:0][["ubigeo", "anio", "semana", "casos_Dengue"]]
    return fi.with_onset_columns(origins, cases, no_history)


# ---------------------------------------------------------------------------
# Block loop (non-OOS path of predict_e3 with arbitrary blocks)
# ---------------------------------------------------------------------------

def predict_blocks(matrices: dict[int, pd.DataFrame], origins: pd.DataFrame, blocks: list[tuple[str, str, int]],
                   seed: int, columns: list[str], hyperparameters: dict,
                   formulation: str = "S4_s3") -> pd.DataFrame:
    """E3 · S4 out-of-sample predictions for each block, with the in-sample alpha."""
    f = sp.FORMULATIONS[formulation]
    if f["probabilidad"] != "binomial_negativa":
        raise ValueError("Solo formulaciones S4")
    H = eh.STRATEGY_HORIZONS
    col_reg = list(columns)
    extra = sp.e3_parameters(hyperparameters)
    margin_all = sp.e3_margin(origins, formulation)
    parts, alphas = [], []
    for block, kind, period in blocks:
        test_sets, cutoff = eh._common_cutoffs(matrices, kind, period)
        fitted = sp.fit_e3(origins, cutoff, seed, formulation, col_reg, [], extra, margin_all)
        counts = sp.predict_count(fitted.regressor, origins[col_reg], f["conteo"], margin_all)
        for step, h in enumerate(H):
            pred = pd.DataFrame({"ubigeo": origins.ubigeo, "semana_inicio": origins[f"semana_inicio_h{h}"],
                                 "origen_cierre_mimo": origins.origen_cierre, "casos_predichos": counts[:, step]})
            test = test_sets[h].merge(pred.dropna(subset=["semana_inicio"]), on=["ubigeo", "semana_inicio"],
                                      how="left", validate="one_to_one")
            if test.casos_predichos.isna().any() or not test.origen_cierre_mimo.eq(test.origen_cierre).all():
                raise ValueError(f"Predicciones incompletas o con origen distinto en {block} h={h}")
            test["probabilidad_brote"] = sp.negative_binomial_probability(
                test.casos_predichos, fitted.alphas[step], test.umbral_brote_casos)
            parts.append(eh._output(test, block, test.casos_predichos, test.probabilidad_brote))
            alphas.append({"bloque": block, "horizonte": h, "alpha": fitted.alphas[step],
                           "filas_entrenamiento": len(fitted.train), "corte": cutoff})
    output = pd.concat(parts, ignore_index=True).assign(estrategia="E3", formulacion=formulation, semilla=seed)
    output.attrs["alfas"] = pd.DataFrame(alphas)
    return output


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def weeks_since_last_case(cases: pd.DataFrame, ubigeo: pd.Series, week: pd.Series,
                          cap: int = fi.di.MAX_WEEKS_WITHOUT_CASE) -> np.ndarray:
    """Weeks from the last week with cases (<= ``week``) to ``week``, capped; recomputed without B3 code."""
    positive = cases.loc[cases.casos_Dengue.gt(0), ["ubigeo", "semana_inicio"]]
    by_district = {u: np.sort(pd.to_datetime(g.semana_inicio).to_numpy()) for u, g in positive.groupby("ubigeo")}
    out = []
    for u, w in zip(ubigeo, pd.to_datetime(week)):
        weeks = by_district.get(u, np.array([], dtype="datetime64[ns]"))
        i = np.searchsorted(weeks, np.datetime64(w), side="right")
        out.append(min(cap, (w - pd.Timestamp(weeks[i - 1])).days // 7) if i else cap)
    return np.asarray(out, float)


def compare_origins(long: pd.DataFrame, v1: pd.DataFrame, columns: list[str] = V1_COLUMNS,
                    atol: float = 1e-12, exception: dict | None = None,
                    cases: pd.DataFrame | None = None) -> dict:
    """G1: ``base_6`` + B3 of the long table against the V1 table on their common origins.

    ``exception`` (amendment G1): rows of ``exception["columna"]`` with the V1 value
    ``valor_v1`` and a close up to ``ultimo_cierre`` are checked against the weeks
    since the last case recomputed from ``cases`` instead of against the V1.
    """
    key = ["ubigeo", "origen_cierre"]
    m = v1[key + columns].merge(long[key + columns], on=key, suffixes=("_v1", "_larga"), how="left",
                                validate="one_to_one", indicator=True)
    diffs, worst, excepted = {}, {}, {}
    for c in columns:
        d = (m[f"{c}_v1"] - m[f"{c}_larga"]).abs()
        both_nan = m[f"{c}_v1"].isna() & m[f"{c}_larga"].isna()
        bad = (d > atol) | (m[f"{c}_v1"].isna() != m[f"{c}_larga"].isna())
        if exception is not None and c == exception["columna"]:
            rows = (m[f"{c}_v1"].eq(exception["valor_v1"])
                    & m.origen_cierre.le(pd.Timestamp(exception["ultimo_cierre"])) & bad)
            sub = m[rows]
            expected = weeks_since_last_case(cases, sub.ubigeo, sub.origen_cierre - pd.Timedelta(days=6))
            ok = (sub[f"{c}_larga"].to_numpy() < exception["valor_v1"]) & (sub[f"{c}_larga"].to_numpy() == expected)
            excepted = {"filas": int(rows.sum()), "distritos": int(sub.ubigeo.nunique()),
                        "coinciden_con_el_recalculo": int(ok.sum())}
            bad = bad & ~rows
            bad.loc[sub.index[~ok]] = True
        diffs[c] = int(bad.sum())
        worst[c] = float(d[~both_nan].max()) if (~both_nan).any() else 0.0
        if bad.any():
            worst[f"{c}_ultimo_origen_distinto"] = str(m.loc[bad, "origen_cierre"].max().date())
    return {"origenes_v1": len(v1), "sin_par_en_la_larga": int(m._merge.ne("both").sum()),
            "filas_distintas": diffs, "diferencia_maxima": worst, "excepcion_G1": excepted,
            "pasa": all(v == 0 for v in diffs.values()) and m._merge.eq("both").all()}


def compare_predictions(pred: pd.DataFrame, saved: pd.DataFrame) -> dict:
    """G2: exact comparison of the uncalibrated predictions (mu and NB2 probability) by key."""
    key = ["ubigeo", "semana_inicio", "horizonte", "bloque"]
    a = pred.assign(semana_inicio=pd.to_datetime(pred.semana_inicio).dt.strftime("%Y-%m-%d"))
    b = saved.assign(semana_inicio=pd.to_datetime(saved.semana_inicio).dt.strftime("%Y-%m-%d"))
    m = a.merge(b, on=key, suffixes=("", "_guardada"), validate="one_to_one")
    diff = {c: float(np.abs(m[c] - m[f"{c}_guardada"]).max()) for c in ("casos_predichos", "probabilidad_brote")}
    return {"filas": len(a), "filas_guardadas": len(b), "cruzadas": len(m), "diferencia_maxima": diff,
            "pasa": len(m) == len(a) == len(b) and all(v == 0 for v in diff.values())}
