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

from denguekay.config.paths import MODELS
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


# ---------------------------------------------------------------------------
# Whole comparison 1a
# ---------------------------------------------------------------------------

V1_SAVED = MODELS / "experimentos" / "fe_hiperparametros" / "fase4" / "predicciones_s4s3_dentro_muestra.csv.gz"
OUTPUT_DIR = MODELS / "experimentos" / "mejora_modelo" / "fase1a"   # not versioned
REPORT_SEASONS = (2010, 2015, 2016, 2017, 2022, 2023, 2024)


def read_saved(path) -> pd.DataFrame:
    """Saved predictions read back exactly (the default CSV parser can move the last bit)."""
    return pd.read_csv(path, dtype={"ubigeo": "string"}, float_precision="round_trip")


def phase1a_inputs() -> dict:
    """Long series, labels, matrices and origins (L) and the gold inputs and V1 origins (R)."""
    import json

    from denguekay.config.paths import GOLD_MANIFEST
    from denguekay.evaluation import variants as fh
    from denguekay.model import frozen_configs as cf

    from phase0_diagnosis import load_integrated, long_case_series, long_labels

    panel = load_integrated()
    cases, audit = long_case_series(panel)
    labels = long_labels(cases)
    matrices = long_matrices(cases, labels)
    rule = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
    ins = fh.inputs(panel, rule)
    series = labels[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue", "brote"]].copy()
    series["semana_inicio"] = pd.to_datetime(series.semana_inicio)
    return {"panel": panel, "casos": cases, "auditoria_historia": audit, "etiquetas": labels, "serie": series,
            "matrices_L": matrices, "origenes_L": long_origins(cases, matrices[2]),
            "matrices_R": ins["matrices"], "origenes_R": cf.origins(panel, ins, rule, configuration=cf.CONFIG_2026_V1),
            "serie_gold": ins["serie"]}


def guards(inp: dict, exception: dict) -> dict:
    """G1 (with the amendment), G2 (R seed 17 against the saved V1) and G3 (labels against gold)."""
    from denguekay.model import frozen_configs as cf

    g1 = compare_origins(inp["origenes_L"], inp["origenes_R"], exception=exception, cases=inp["casos"])
    c = cf.CONFIG_2026_V1
    r17 = predict_blocks(inp["matrices_R"], inp["origenes_R"], seasonal_blocks(2021), cf.DEPLOYMENT_SEED,
                         c["columnas"], c["hiperparametros"])
    saved = read_saved(V1_SAVED)
    g2 = compare_predictions(r17, saved[saved.semilla.eq(cf.DEPLOYMENT_SEED)])
    gold = inp["serie_gold"][["ubigeo", "anio", "semana", "brote"]]
    check = inp["etiquetas"].merge(gold, on=["ubigeo", "anio", "semana"], suffixes=("_larga", "_gold"))
    g3 = {"filas": len(check), "filas_gold": len(gold), "distintas": int(check.brote_larga.ne(check.brote_gold).sum())}
    g3["pasa"] = g3["filas"] == g3["filas_gold"] and g3["distintas"] == 0
    return {"G1": g1, "G2": g2, "G3": g3}


def run_variant(matrices, origins, blocks, series, seeds) -> dict:
    """Predictions and protocol evaluation per seed for the V1 configuration."""
    from denguekay.evaluation import protocol as pa
    from denguekay.model import frozen_configs as cf

    c = cf.CONFIG_2026_V1
    preds, evals = {}, {}
    for seed in seeds:
        preds[seed] = predict_blocks(matrices, origins, blocks, seed, c["columnas"], c["hiperparametros"])
        evals[seed] = pa.evaluate(preds[seed], series)
    return {"predicciones": preds, "evaluaciones": evals}


def _blocks_of(seasons) -> list[str]:
    return [f"temporada_{s}" for s in seasons]


def decision_1a(L: dict, R: dict) -> dict:
    """Preregistered verdict of comparison 1a (``preregistration.decide_phase1a``)."""
    import preregistration as pr
    from denguekay.evaluation import protocol as pa

    med_l = pa.seed_median([e["metricas"] for e in L["evaluaciones"].values()])
    med_r = pa.seed_median([e["metricas"] for e in R["evaluaciones"].values()])
    ranges = pa.tie_threshold(pa.seed_ranges([e["metricas"] for e in L["evaluaciones"].values()]),
                              pa.seed_ranges([e["metricas"] for e in R["evaluaciones"].values()]))
    seed = pr.SEEDS[0]
    lead = pr.lead_time_difference_multi(L["evaluaciones"][seed]["antelacion"], R["evaluaciones"][seed]["antelacion"],
                                         "alerta_050", seasons=pr.PHASE1A_SEASONS)
    blocks = _blocks_of(pr.PHASE1A_SEASONS)
    verdict = pr.decide_phase1a(med_l[med_l.bloque.isin(blocks)], med_r[med_r.bloque.isin(blocks)],
                                ranges[ranges.bloque.isin(blocks)], lead)
    adopt = bool(verdict.veredicto.isin(pr.PHASE1A_ADOPT).all())
    deltas = med_l.merge(med_r, on=["horizonte", "bloque"], suffixes=("_L", "_R"))
    deltas = deltas[deltas.bloque.isin([*blocks, f"temporada_{pr.CONTRAST_SEASON}"])]
    cols = ["horizonte", "bloque", "positivos_L"] + [f"{m}_{v}" for m in ("f1_050", "recall_050", "precision_050",
                                                                           "auprc", "brier", "razon_mae", "razon_rmse")
                                                      for v in ("L", "R")]
    return {"veredicto": verdict, "antelacion": lead, "umbral_empate": ranges[ranges.bloque.isin(blocks)],
            "metricas_L_R": deltas[cols], "adopta_L": adopt, "medianas_L": med_l, "medianas_R": med_r}


def seed_median_of(tables: dict[int, pd.DataFrame], keys: list[str]) -> pd.DataFrame:
    every = pd.concat(tables, names=["semilla"]).reset_index(level=0)
    numeric = [c for c in every.select_dtypes("number").columns if c not in keys + ["semilla"]]
    g = every.groupby(keys, observed=True)[numeric]
    return g.median().join((g.max() - g.min()).add_suffix("_rango")).reset_index()


def readings_1a(L: dict, R: dict, V1: dict, series: pd.DataFrame, med_l: pd.DataFrame) -> dict:
    """Readings that do not decide (preregistered list)."""
    import preregistration as pr
    from denguekay.evaluation import protocol as pa
    from denguekay.model import frozen_configs as cf

    report = _blocks_of(REPORT_SEASONS)
    seed = pr.SEEDS[0]
    rng_l = pa.seed_ranges([e["metricas"] for e in L["evaluaciones"].values()])
    by_season = med_l[med_l.bloque.isin(report)].merge(
        rng_l[["horizonte", "bloque", "f1_050", "razon_mae"]].rename(
            columns={"f1_050": "f1_050_rango", "razon_mae": "razon_mae_rango"}), on=["horizonte", "bloque"])
    hu = sp.hu0007_4_compliance(med_l[med_l.bloque.isin(report)]).merge(
        med_l[["horizonte", "bloque", "positivos"]], on=["horizonte", "bloque"])
    hu["evaluable"] = hu.positivos.map(lambda n: cf.evaluable(int(n), "brote"))
    med_v1 = pa.seed_median([e["metricas"] for e in V1["evaluaciones"].values()])
    med_r = pa.seed_median([e["metricas"] for e in R["evaluaciones"].values()])
    cmp_cols = ["horizonte", "bloque", "positivos", "f1_050", "recall_050", "brier", "brier_sin_calibrar", "razon_mae"]
    calib = med_v1[cmp_cols].merge(med_r[cmp_cols], on=["horizonte", "bloque", "positivos"], suffixes=("_V1", "_R"))
    calib = calib[calib.bloque.isin(_blocks_of((2022, 2023, 2024)))]
    recall = seed_median_of({s: sp.recall_by_week_type(e["datos"], series) for s, e in L["evaluaciones"].items()},
                            ["horizonte", "bloque", "tipo"])
    lead = L["evaluaciones"][seed]["antelacion_ic"]
    lead = lead[lead.bloque.isin(report + ["seleccion_2022_2023"])]
    lead = lead[lead.alerta.isin(["alerta_050", "alerta_persistencia"])]
    phases = seed_median_of({s: e["errores_por_fase"] for s, e in L["evaluaciones"].items()},
                            ["horizonte", "bloque", "fase"])
    calibration = L["evaluaciones"][seed]["calibracion"]
    return {"metricas_por_temporada_L": by_season, "hu0007_4_L": hu, "calibracion_V1_frente_a_R": calib,
            "recall_por_tipo_L": recall[recall.bloque.isin(report)], "antelacion_L_semilla_17": lead,
            "conteo_por_fase_L": phases[phases.bloque.isin(report)],
            "calibradores_L_semilla_17": calibration}
