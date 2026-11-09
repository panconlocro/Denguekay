"""Phase 0 of the model improvement study: diagnosis and ceiling of the V2.

Read-only. It uses the out-of-sample predictions of the V2 saved by study 05
(``F_A3``: 5 seeds, h=2, 3, 4, blocks 2021-2025) and the frozen protocol
(``denguekay.evaluation.protocol.evaluate``); nothing is trained or written to
``data/``.

Week states (retrospective, per district and target week, from the labels):

- ``inicio_limpio``: ``brote`` week among the first ``ONSET_WEEKS`` weeks of an
  episode without ``brote`` in the previous 8 weeks (same definition as
  ``probabilistic_output.recall_by_week_type``);
- ``en_curso``: any other ``brote`` week;
- ``bajada``: week without ``brote`` up to ``DECAY_WEEKS`` weeks after the
  district's last ``brote`` week;
- ``valle``: the rest of the weeks without ``brote``.

The long history (2000-2025) follows Rosa's decision of 2026-11-02: a district
without a record in a week of ``epi_piura_semanal.csv`` had 0 cases.
"""

import numpy as np
import pandas as pd

from denguekay.config.paths import MODELS, SILVER_EPI_HISTORICAL, UBIGEO_CATALOG
from denguekay.data.calendar import mmwr_epi_week
from denguekay.data.loading import load_integrated
from denguekay.data.validation.forecast_contract import KEY
from denguekay.evaluation import episodes as diag
from denguekay.evaluation import onsets as ons
from denguekay.evaluation import protocol as pa
from denguekay.features.gold import build_labels
from denguekay.features.outbreak_label import SeasonalOutbreakConfig, future_outbreak_threshold
from denguekay.model import probabilistic_output as sp

V2_PREDICTIONS = MODELS / "experimentos" / "fe_hiperparametros" / "complemento_clima" / "predicciones_F_A3.csv.gz"
# Outbreak rule of gold (manifest_fase6.json -> regla_brote).
OUTBREAK_RULE = {"multiplicador": 1.5, "anios_previos": 5, "minimo_casos": 2}
ONSET_WEEKS = 2
DECAY_WEEKS = 8
STATES = ("inicio_limpio", "en_curso", "bajada", "valle")
NEAR_CUTOFF = (0.40, 0.50)
HU_BLOCKS = ("temporada_2022", "temporada_2023", "temporada_2024")
HISTORY_START = 2000


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def outbreak_config() -> SeasonalOutbreakConfig:
    return SeasonalOutbreakConfig(OUTBREAK_RULE["multiplicador"], OUTBREAK_RULE["anios_previos"],
                                  OUTBREAK_RULE["minimo_casos"])


def panel_series() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Integrated panel 2017-2025 and its series with the gold label (as in ``variants.inputs``)."""
    panel = load_integrated()
    labels = build_labels(panel, outbreak_config())
    series = panel[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]].merge(
        labels[["ubigeo", "anio", "semana", "brote", "umbral_brote_casos"]], on=["ubigeo", "anio", "semana"])
    series["semana_inicio"] = pd.to_datetime(series.semana_inicio)
    return panel, series


def v2_predictions(path=V2_PREDICTIONS) -> dict[int, pd.DataFrame]:
    """Saved OOS predictions of the V2, one table per seed."""
    pred = pd.read_csv(path, dtype={"ubigeo": "string"})
    pred["ubigeo"] = pred.ubigeo.astype(str)
    return {int(s): g.drop(columns="semilla").reset_index(drop=True) for s, g in pred.groupby("semilla")}


def evaluate_seeds(predictions: dict[int, pd.DataFrame], series: pd.DataFrame) -> dict[int, dict]:
    """Frozen protocol (chronological Platt, p >= 0.50) per seed."""
    return {s: pa.evaluate(p, series) for s, p in predictions.items()}


# ---------------------------------------------------------------------------
# Week states and errors per state
# ---------------------------------------------------------------------------

def week_states(series: pd.DataFrame, onset_weeks: int = ONSET_WEEKS,
                decay_weeks: int = DECAY_WEEKS) -> pd.DataFrame:
    """State of each district-week (see the module docstring)."""
    s = series[["ubigeo", "semana_inicio", "brote"]].sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
    eps = diag.episodes(s)
    clean = eps[eps.semanas_previas_sin_brote >= diag.NO_PREVIOUS_OUTBREAK]
    onset_keys = {(u, i + pd.Timedelta(weeks=k)) for u, i in zip(clean.ubigeo, clean.inicio)
                  for k in range(onset_weeks)}
    last_outbreak = s.semana_inicio.where(s.brote.eq(1)).groupby(s.ubigeo).ffill()
    since = (s.semana_inicio - last_outbreak).dt.days / 7
    is_onset = np.array([(u, w) in onset_keys for u, w in zip(s.ubigeo, s.semana_inicio)])
    state = np.where(s.brote.eq(1), np.where(is_onset, "inicio_limpio", "en_curso"),
                     np.where(since.le(decay_weeks), "bajada", "valle"))
    return s[["ubigeo", "semana_inicio"]].assign(estado=pd.Categorical(state, categories=STATES))


def errors_by_state(data: pd.DataFrame, states: pd.DataFrame) -> pd.DataFrame:
    """Alerts and count errors per horizon, block and state (one seed, evaluated blocks only)."""
    d = data[data.probabilidad_calibrada.notna()].merge(states, on=["ubigeo", "semana_inicio"],
                                                        how="left", validate="many_to_one")
    if d.estado.isna().any():
        raise ValueError("Filas sin estado")
    rows = []
    for (h, block, state), g in d.groupby(["horizonte", "bloque", "estado"], observed=True):
        alert, pers, y = g.alerta_050.to_numpy(bool), g.alerta_persistencia.to_numpy(bool), g.brote.to_numpy(int)
        e_m, e_p = (g.casos_predichos - g.casos_Dengue).abs(), (g.persistencia - g.casos_Dengue).abs()
        rows.append({"horizonte": h, "bloque": block, "estado": state, "n": len(g), "positivos": int(y.sum()),
                     "vp": int((alert & (y == 1)).sum()), "fn": int((~alert & (y == 1)).sum()),
                     "fp": int((alert & (y == 0)).sum()),
                     "recall": float(alert[y == 1].mean()) if y.any() else np.nan,
                     "tasa_alerta": float(alert.mean()),
                     "recall_persistencia": float(pers[y == 1].mean()) if y.any() else np.nan,
                     "tasa_alerta_persistencia": float(pers.mean()),
                     "mae": float(e_m.mean()), "mae_persistencia": float(e_p.mean()),
                     "razon_mae": float(e_m.mean() / e_p.mean()) if e_p.mean() else np.nan})
    table = pd.DataFrame(rows)
    fn_total = table.groupby(["horizonte", "bloque"]).fn.transform("sum")
    fp_total = table.groupby(["horizonte", "bloque"]).fp.transform("sum")
    table["fraccion_fn"] = table.fn / fn_total.replace(0, np.nan)
    table["fraccion_fp"] = table.fp / fp_total.replace(0, np.nan)
    return table


# ---------------------------------------------------------------------------
# Calibration and diagnostic ceiling
# ---------------------------------------------------------------------------

def expected_calibration_error(y, p, n_bins: int = 10) -> float:
    """Weighted mean |mean p - observed frequency| over equal-width bins."""
    c = diag.reliability_curve(y, p, n_bins)
    return float((c.n * (c.prob_media - c.frecuencia_observada).abs()).sum() / c.n.sum())


def oracle_f1(y, p_raw) -> dict:
    """Diagnostic F1 ceilings with calibrators fitted **on the evaluated block itself**.

    Not a valid evaluation: it only says how much F1 at p >= 0.50 a perfect
    monotonic recalibration of that season could recover. ``f1_mejor_umbral``
    is the upper bound of any monotonic transformation (best threshold).
    """
    from sklearn.isotonic import IsotonicRegression

    y, p_raw = np.asarray(y, int), np.asarray(p_raw, float)

    def f1(alert):
        tp = int((alert & (y == 1)).sum())
        return 2 * tp / (alert.sum() + y.sum()) if (alert.sum() + y.sum()) else 0.0

    iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(p_raw, y).predict(p_raw)
    platt = pa.fit_platt(p_raw, y).predict_proba(pa.platt_logit(p_raw).reshape(-1, 1))[:, 1]
    return {"f1_oraculo_isotonica": f1(iso >= pa.ALERT_THRESHOLD),
            "f1_oraculo_platt": f1(platt >= pa.ALERT_THRESHOLD),
            "f1_mejor_umbral": best_threshold_f1(y, p_raw)}


def best_threshold_f1(y, p) -> float:
    """Highest F1 of ``p >= t`` over every distinct value ``t`` of ``p`` (ties stay together)."""
    y, p = np.asarray(y, int), np.asarray(p, float)
    order = np.argsort(-p, kind="stable")
    p_sorted, tp = p[order], np.cumsum(y[order])
    last_of_value = np.r_[p_sorted[1:] != p_sorted[:-1], True]
    k = np.arange(1, len(p) + 1)[last_of_value]
    return float(np.max(2 * tp[last_of_value] / (k + y.sum()))) if y.any() else 0.0


def calibration_summary(data: pd.DataFrame) -> pd.DataFrame:
    """Per horizon and block: calibration, weeks near the cutoff and the F1 ceilings (one seed)."""
    rows = []
    for (h, block), g in data[data.probabilidad_calibrada.notna()].groupby(["horizonte", "bloque"]):
        y, pc, pr = g.brote.to_numpy(int), g.probabilidad_calibrada.to_numpy(float), g.probabilidad_brote.to_numpy(float)
        near = (pc >= NEAR_CUTOFF[0]) & (pc < NEAR_CUTOFF[1])
        tp = int((g.alerta_050.to_numpy(bool) & (y == 1)).sum())
        alerts = int(g.alerta_050.sum())
        rows.append({"horizonte": h, "bloque": block, "n": len(g), "positivos": int(y.sum()),
                     "prevalencia": float(y.mean()), "prob_media_calibrada": float(pc.mean()),
                     "prob_media_sin_calibrar": float(pr.mean()),
                     "brier": float(np.mean((pc - y) ** 2)), "brier_sin_calibrar": float(np.mean((pr - y) ** 2)),
                     "ece": expected_calibration_error(y, pc), "ece_sin_calibrar": expected_calibration_error(y, pr),
                     "brote_en_040_050": int((near & (y == 1)).sum()), "no_brote_en_040_050": int((near & (y == 0)).sum()),
                     "f1_050": 2 * tp / (alerts + y.sum()) if (alerts + y.sum()) else 0.0,
                     "fraccion_sin_calibrar_bajo_eps": float((pr < pa.EPS).mean()),
                     **oracle_f1(y, pr)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Persistence: how much of the outbreak weeks it already gets
# ---------------------------------------------------------------------------

def persistence_margin(data: pd.DataFrame) -> pd.DataFrame:
    """Overlap of model and persistence alerts on ``brote`` weeks (one seed)."""
    rows = []
    for (h, block), g in data[data.probabilidad_calibrada.notna() & data.brote.eq(1)].groupby(["horizonte", "bloque"]):
        m, p = g.alerta_050.to_numpy(bool), g.alerta_persistencia.to_numpy(bool)
        n = len(g)
        rows.append({"horizonte": h, "bloque": block, "positivos": n,
                     "recall_persistencia": float(p.mean()), "recall_modelo": float(m.mean()),
                     "ambos": float((m & p).mean()), "solo_persistencia": float((~m & p).mean()),
                     "solo_modelo": float((m & ~p).mean()), "ninguno": float((~m & ~p).mean()),
                     "recall_modelo_donde_persistencia_falla": float(m[~p].mean()) if (~p).any() else np.nan})
    return pd.DataFrame(rows)


def seed_median_table(tables: dict[int, pd.DataFrame], keys: list[str]) -> pd.DataFrame:
    """Median and range across seeds of each numeric column, per ``keys``."""
    every = pd.concat(tables, names=["semilla"]).reset_index(level=0)
    numeric = [c for c in every.select_dtypes("number").columns if c not in keys + ["semilla"]]
    grouped = every.groupby(keys, observed=True)[numeric]
    med = grouped.median()
    rng = (grouped.max() - grouped.min()).add_suffix("_rango")
    return med.join(rng).reset_index()


def hu0007_4(evaluations: dict[int, dict]) -> pd.DataFrame:
    """HU0007-4 per cell with the seed median (as in study 05)."""
    med = pa.seed_median([r["metricas"] for r in evaluations.values()])
    table = sp.hu0007_4_compliance(med[med.bloque.isin(HU_BLOCKS)])
    return table.merge(med[["horizonte", "bloque", "positivos"]], on=["horizonte", "bloque"])


# ---------------------------------------------------------------------------
# History before 2017
# ---------------------------------------------------------------------------

def piura_ubigeos() -> list[str]:
    catalog = pd.read_csv(UBIGEO_CATALOG, dtype={"ubigeo": "string"})
    return sorted(catalog.ubigeo.astype(str).str.zfill(6))


def week_grid(first_year: int, last_year: int) -> pd.DataFrame:
    """Every MMWR week (Sunday start) of the epidemiological years ``first_year..last_year``."""
    sundays = pd.Series(pd.date_range(f"{first_year - 1}-12-25", f"{last_year + 1}-01-07", freq="W-SUN"))
    weeks = mmwr_epi_week(sundays)
    grid = pd.DataFrame({"semana_inicio": sundays, "anio": weeks.anio_epi, "semana": weeks.semana_epi})
    return grid[grid.anio.between(first_year, last_year)].reset_index(drop=True)


def long_case_series(panel: pd.DataFrame, history_path=SILVER_EPI_HISTORICAL,
                     start: int = HISTORY_START) -> tuple[pd.DataFrame, dict]:
    """Cases per district-week ``start``-2025: silver epi before the panel, the panel from 2017.

    Absent district-weeks before the panel are 0 cases (Rosa, 2026-11-02).
    Returns the series and a small audit (rows outside the MMWR grid, silver vs
    panel agreement in the overlapping years).
    """
    ubigeos = piura_ubigeos()
    first_panel = int(panel.anio.min())
    hist = pd.read_csv(history_path, dtype={"ubigeo": "string"})
    hist["ubigeo"] = hist.ubigeo.astype(str).str.zfill(6)
    hist = hist[hist.ubigeo.isin(ubigeos)]
    grid = week_grid(start, first_panel - 1)
    full = pd.MultiIndex.from_product([ubigeos, range(len(grid))], names=["ubigeo", "i"]).to_frame(index=False)
    full = full.join(grid, on="i").drop(columns="i")
    early = hist[hist.anio.between(start, first_panel - 1)]
    merged = full.merge(early, on=["ubigeo", "anio", "semana"], how="left", validate="one_to_one")
    outside = early.merge(grid[["anio", "semana"]], on=["anio", "semana"], how="left", indicator=True)
    merged["casos_Dengue"] = merged.casos_Dengue.fillna(0).astype(int)
    recent = panel[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]].copy()
    recent["semana_inicio"] = pd.to_datetime(recent.semana_inicio)
    overlap = hist[hist.anio.ge(first_panel)].merge(recent, on=KEY, how="outer", suffixes=("_silver", "_panel"))
    overlap = overlap[overlap.anio.le(hist.anio.max())]
    diff = overlap.casos_Dengue_silver.fillna(0) - overlap.casos_Dengue_panel.fillna(0)
    audit = {"filas_silver_fuera_de_la_grilla": int(outside._merge.eq("left_only").sum()),
             "casos_silver_fuera_de_la_grilla": int(outside.loc[outside._merge.eq("left_only"), "casos_Dengue"].sum()),
             "filas_solapadas_distintas": int(diff.ne(0).sum()),
             "anios_solapados": [first_panel, int(hist.anio.max())]}
    series = pd.concat([merged[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]], recent],
                       ignore_index=True).sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
    return series, audit


def long_labels(cases: pd.DataFrame, start: int = HISTORY_START) -> pd.DataFrame:
    """Gold outbreak rule from ``start + anios_previos`` onwards, with ``future_outbreak_threshold``."""
    rule = OUTBREAK_RULE
    first_label = start + rule["anios_previos"]
    targets = cases[cases.anio.ge(first_label)].reset_index(drop=True)
    threshold = future_outbreak_threshold(cases, None, targets, multiplicador=rule["multiplicador"],
                                          anios_previos=rule["anios_previos"])
    out = targets.assign(umbral_brote_casos=threshold.to_numpy())
    out["brote"] = ((out.casos_Dengue > out.umbral_brote_casos)
                    & (out.casos_Dengue >= rule["minimo_casos"])).astype("int8")
    return out


def history_summary(labels: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cases and ``brote`` weeks per calendar year; clean onsets per season."""
    by_year = labels.groupby("anio").agg(casos=("casos_Dengue", "sum"), semanas_brote=("brote", "sum"),
                                         distritos_con_brote=("brote", lambda b: int(
                                             labels.loc[b.index[b.eq(1)], "ubigeo"].nunique()))).reset_index()
    onsets = ons.clean_onsets(labels)
    seasons = labels.assign(temporada=ons.with_season(labels)).groupby("temporada").agg(
        casos=("casos_Dengue", "sum"), semanas_brote=("brote", "sum"), semanas=("semana", "size")).reset_index()
    counts = onsets.groupby("temporada").agg(inicios_limpios=("id_inicio", "size"),
                                             verificables=("verificable", "sum"),
                                             distritos=("ubigeo", "nunique")).reset_index()
    seasons = seasons.merge(counts, on="temporada", how="left").fillna({"inicios_limpios": 0, "verificables": 0,
                                                                         "distritos": 0})
    seasons["semanas"] = (seasons.semanas / labels.ubigeo.nunique()).round().astype(int)
    return by_year, seasons


# ---------------------------------------------------------------------------
# Whole phase, outputs and figure
# ---------------------------------------------------------------------------

def run_phase0() -> dict:
    """Every phase 0 table (seed medians and ranges) plus the inputs needed to plot."""
    panel, series = panel_series()
    evaluations = evaluate_seeds(v2_predictions(), series)
    states = week_states(series)
    cases, audit = long_case_series(panel)
    labels = long_labels(cases)
    check = labels[labels.anio.ge(int(panel.anio.min()))].merge(
        series, on=["ubigeo", "anio", "semana"], suffixes=("_larga", "_gold"), validate="one_to_one")
    audit.update({"filas_etiqueta_comparadas_con_gold": len(check),
                  "etiquetas_distintas_de_gold": int(check.brote_larga.ne(check.brote_gold).sum()),
                  "umbral_diferencia_maxima": float((check.umbral_brote_casos_larga
                                                     - check.umbral_brote_casos_gold).abs().max())})
    by_year, by_season = history_summary(labels)
    seeds = evaluations.items()
    return {
        "evaluaciones": evaluations, "serie": series,
        "hu0007_4": hu0007_4(evaluations),
        "errores_por_estado": seed_median_table({s: errors_by_state(r["datos"], states) for s, r in seeds},
                                                ["horizonte", "bloque", "estado"]),
        "calibracion": seed_median_table({s: calibration_summary(r["datos"]) for s, r in seeds},
                                         ["horizonte", "bloque"]),
        "persistencia": seed_median_table({s: persistence_margin(r["datos"]) for s, r in seeds},
                                          ["horizonte", "bloque"]),
        "historia_anual": by_year, "historia_temporadas": by_season, "auditoria_historia": audit,
    }


def reliability_figure(data: pd.DataFrame, blocks=HU_BLOCKS, n_bins: int = 10):
    """Reliability of the calibrated probability per season and horizon (one seed)."""
    import matplotlib.pyplot as plt

    horizons = sorted(data.horizonte.unique())
    fig, axes = plt.subplots(1, len(horizons), figsize=(5.5 * len(horizons), 5), squeeze=False)
    for j, h in enumerate(horizons):
        ax = axes[0, j]
        ax.plot([0, 1], [0, 1], color="grey", linestyle="--", label="Calibración perfecta")
        for block in blocks:
            g = data[data.horizonte.eq(h) & data.bloque.eq(block)]
            c = diag.reliability_curve(g.brote, g.probabilidad_calibrada, n_bins)
            ax.plot(c.prob_media, c.frecuencia_observada, marker="o",
                    label=f"{block.replace('temporada_', 'temp. ')} ({int(g.brote.sum())} semanas brote)")
        ax.axvline(pa.ALERT_THRESHOLD, color="black", linewidth=0.8)
        ax.set_xlabel("Probabilidad calibrada de brote (Platt)")
        ax.set_ylabel("Frecuencia observada de brote")
        ax.set_title(f"h={h}")
        ax.legend(fontsize=8)
    fig.suptitle("V2: fiabilidad de la probabilidad calibrada por temporada (semilla 17)")
    fig.tight_layout()
    return fig
