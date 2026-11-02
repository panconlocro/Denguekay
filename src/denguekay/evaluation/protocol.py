"""Preregistered evaluation protocol of the multi-horizon study (phase 2).

It receives out-of-sample predictions in the standard format (one row per
horizon x block x target district-week) and applies, without looking at the
evaluated season:

1. **Chronological calibration** of the outbreak probability: each block's
   calibrator is fitted with predictions of earlier blocks whose labels closed
   before the block's first origin (2021 -> 2022; 2021-2022 -> 2023; ...). 2021
   has no calibrator and is not evaluated on alerts.
2. **HU alert rule:** alert if the calibrated probability is >= 0.50; risk levels
   with cutoffs 0.25 / 0.50 / 0.75.
3. **Metrics:** P/R/F1 at 0.50, AUPRC, Brier and reliability per season,
   MAE/RMSE against persistence with a breakdown per curve phase, and lead time
   on clean onsets with a bootstrap interval per episode.
4. **Decision rule** between two architectures with the seed ranges.

The threshold that maximises F1 is only computed as a **diagnosis** (with
earlier calibration, never with the evaluated block) and plays no part in the
decision.
"""

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from denguekay.evaluation import episodes as diag
from denguekay.evaluation.metrics import (
    alerts_from_counts, alert_metrics, count_metrics, select_f1_threshold,
)
from denguekay.model.train import MIN_OUTBREAK_CASES
from denguekay.serving.risk import LEVELS
from denguekay.data.validation.forecast_contract import KEY

INITIAL_CALIBRATION_BLOCK = "temporada_2021"
SELECTION_BLOCKS = ("temporada_2022", "temporada_2023")
CONTRAST_BLOCK = "temporada_2024"
COUNT_SENSITIVITY_BLOCK = "calendario_2025"
ALERT_THRESHOLD = 0.50
RISK_CUTOFFS = {"medio": 0.25, "alto": 0.50, "muy_alto": 0.75}
CALIBRATION_METHOD = "platt"
SEEDS = (17, 29, 41, 53, 67)
MIN_LEAD_TIME = 2
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261020
EPS = 1e-6
PREDICTION_COLUMNS = [*KEY, "semana_inicio", "origen_cierre", "horizonte", "bloque",
                       "casos_Dengue", "brote", "umbral_brote_casos", "persistencia"]
# Metrics where higher is better (+1) or worse (-1). RMSE is reported, it does not decide.
DIRECTION = {"f1_050": 1, "auprc": 1, "brier": -1, "razon_mae": -1}
PRIMARY = ("f1_050",)
GUARDS = ("auprc", "brier", "razon_mae")


def validate_predictions(pred: pd.DataFrame) -> pd.DataFrame:
    """Require the standard format, unique keys and origin causality."""
    missing = set(PREDICTION_COLUMNS) - set(pred)
    if missing:
        raise ValueError(f"Faltan columnas de predicción: {sorted(missing)}")
    if "probabilidad_brote" not in pred and "casos_predichos" not in pred:
        raise ValueError("Se necesita probabilidad_brote o casos_predichos")
    data = pred.copy()
    if not data.ubigeo.map(lambda u: isinstance(u, str)).all():
        raise ValueError("ubigeo debe ser texto de seis dígitos, no número")
    data["ubigeo"] = data.ubigeo.astype("string")
    if not data.ubigeo.str.fullmatch(r"\d{6}").all():
        raise ValueError("ubigeo debe ser texto de seis dígitos")
    for col in ("semana_inicio", "origen_cierre"):
        data[col] = pd.to_datetime(data[col])
    if data.duplicated(["horizonte", "bloque", *KEY]).any():
        raise ValueError("Distrito-semanas duplicadas en un bloque")
    if not data.origen_cierre.lt(data.semana_inicio).all():
        raise ValueError("Fuga temporal: origen_cierre debe ser anterior a semana_inicio")
    if "probabilidad_brote" in data:
        p = data.probabilidad_brote
        if p.isna().any() or not p.between(0, 1).all():
            raise ValueError("Probabilidades fuera de [0, 1]")
    return data


# ---------------------------------------------------------------------------
# Chronological calibration
# ---------------------------------------------------------------------------

def platt_logit(p) -> np.ndarray:
    """Logit of the probability clipped to [EPS, 1 - EPS]: the input of Platt."""
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def fit_platt(p: np.ndarray, y: np.ndarray) -> LogisticRegression:
    """Platt: logistic regression of ``y`` on ``platt_logit(p)``; its ``coef_`` and ``intercept_`` define it."""
    return LogisticRegression(C=1e6, max_iter=1000).fit(platt_logit(p).reshape(-1, 1), np.asarray(y, int))


def fit_calibrator(p: np.ndarray, y: np.ndarray, method: str = CALIBRATION_METHOD):
    """Return a monotonic function p -> calibrated p fitted with (p, y)."""
    p, y = np.asarray(p, float), np.asarray(y, int)
    if len(np.unique(y)) < 2:
        raise ValueError("El calibrador necesita dos clases")
    if method == "platt":
        model = fit_platt(p, y)

        def calibrate(q):
            return model.predict_proba(platt_logit(q).reshape(-1, 1))[:, 1]
        return calibrate
    if method == "isotonica":
        model = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(p, y)
        return lambda q: model.predict(np.asarray(q, float))
    if method == "ninguno":
        return lambda q: np.asarray(q, float)
    raise ValueError(f"Método de calibración desconocido: {method}")


def block_cutoff(block: pd.DataFrame) -> pd.Timestamp:
    """First origin of the block: origin close of its first target week."""
    first = block.semana_inicio.min()
    return block.loc[block.semana_inicio.eq(first), "origen_cierre"].min()


def calibrate_chronologically(pred: pd.DataFrame, method: str = CALIBRATION_METHOD
                              ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add ``probabilidad_calibrada`` and the diagnostic F1 threshold per block.

    For each horizon and block, the calibrator uses rows of blocks that start
    earlier, with a label closed (``semana_inicio + 6 days``) by the block's first
    origin. Without two available classes the block stays without a calibrated
    probability (season 2021).
    """
    data = validate_predictions(pred)
    data["probabilidad_calibrada"] = np.nan
    data["umbral_diagnostico_f1"] = np.nan
    record = []
    for h, by_h in data.groupby("horizonte"):
        onsets = by_h.groupby("bloque").semana_inicio.min().sort_values()
        for block, start in onsets.items():
            idx = by_h.index[by_h.bloque.eq(block)]
            cutoff = block_cutoff(by_h.loc[idx])
            previous = by_h[by_h.bloque.map(onsets).lt(start)]
            available = previous[(previous.semana_inicio + pd.Timedelta(days=6)).le(cutoff)]
            row = {"horizonte": h, "bloque": block, "corte": cutoff, "metodo": method,
                    "filas_calibracion": len(available),
                    "positivos_calibracion": int(available.brote.sum()),
                    "etiquetas_no_cerradas": len(previous) - len(available)}
            if available.brote.nunique() == 2:
                calibrate = fit_calibrator(available.probabilidad_brote, available.brote, method)
                data.loc[idx, "probabilidad_calibrada"] = calibrate(data.loc[idx, "probabilidad_brote"])
                diagnosis = select_f1_threshold(
                    available.brote.to_numpy(int), calibrate(available.probabilidad_brote))
                data.loc[idx, "umbral_diagnostico_f1"] = diagnosis["umbral"]
                row["ultima_etiqueta_usada"] = available.semana_inicio.max() + pd.Timedelta(days=6)
            record.append(row)
    return data, pd.DataFrame(record)


def risk_levels(p: pd.Series, cutoffs: dict = RISK_CUTOFFS) -> pd.Categorical:
    """Levels bajo/medio/alto/muy_alto with left-closed intervals."""
    edges = [-np.inf, cutoffs["medio"], cutoffs["alto"], cutoffs["muy_alto"], np.inf]
    return pd.cut(p, bins=edges, labels=list(LEVELS), right=False)


# ---------------------------------------------------------------------------
# Metrics per block
# ---------------------------------------------------------------------------

def add_protocol_alerts(data: pd.DataFrame) -> pd.DataFrame:
    """Alerts with calibrated p >= 0.50, the case rule and persistence."""
    output = data.copy()
    limit = output.umbral_brote_casos.to_numpy(float)
    output["alerta_050"] = output.probabilidad_calibrada.ge(ALERT_THRESHOLD) if "probabilidad_calibrada" in output else False
    output["alerta_diagnostico_f1"] = (output.probabilidad_calibrada.ge(output.umbral_diagnostico_f1)
                                       if "probabilidad_calibrada" in output else False)
    if "casos_predichos" in output:
        output["alerta_regresion"] = alerts_from_counts(
            output.casos_predichos.to_numpy(float), limit, MIN_OUTBREAK_CASES)
    output["alerta_persistencia"] = alerts_from_counts(
        output.persistencia.to_numpy(float), limit, MIN_OUTBREAK_CASES)
    return output


def metrics_by_block(data: pd.DataFrame) -> pd.DataFrame:
    """One row per horizon and block with every protocol metric."""
    rows = []
    for (h, block), g in data.groupby(["horizonte", "bloque"]):
        y = g.brote.to_numpy(int)
        row = {"horizonte": h, "bloque": block, "n": len(g), "positivos": int(y.sum())}
        if "probabilidad_calibrada" in g and g.probabilidad_calibrada.notna().all():
            pc = g.probabilidad_calibrada.to_numpy(float)
            m = alert_metrics(y, g.alerta_050.to_numpy(bool), score=pc)
            row.update({f"{k}_050": m[k] for k in ("vp", "fp", "fn", "precision", "recall", "f1")})
            row["auprc"] = m["auprc"]
            row["brier"] = float(np.mean((pc - y) ** 2))
            row["brier_sin_calibrar"] = float(np.mean((g.probabilidad_brote - y) ** 2))
            row["prob_media_calibrada"] = float(pc.mean())
            row["prevalencia"] = float(y.mean())
            levels = risk_levels(g.probabilidad_calibrada)
            for level in LEVELS:
                in_level = levels == level
                row[f"n_{level}"] = int(in_level.sum())
                row[f"tasa_brote_{level}"] = float(y[in_level].mean()) if in_level.any() else None
            d = alert_metrics(y, g.alerta_diagnostico_f1.to_numpy(bool))
            row["diagnostico_umbral_f1"] = float(g.umbral_diagnostico_f1.iloc[0])
            row["diagnostico_f1"] = d["f1"]
        if "alerta_regresion" in g:
            m = alert_metrics(y, g.alerta_regresion.to_numpy(bool))
            row.update({f"{k}_regresion": m[k] for k in ("precision", "recall", "f1")})
        limit = np.maximum(g.umbral_brote_casos.to_numpy(float), MIN_OUTBREAK_CASES)
        m = alert_metrics(y, g.alerta_persistencia.to_numpy(bool),
                            score=g.persistencia.to_numpy(float) - limit)
        row.update({f"{k}_persistencia": m[k] for k in ("precision", "recall", "f1", "auprc")})
        if "estacional" in g and g.estacional.notna().all():
            est = g.estacional.to_numpy(float)
            m = alert_metrics(y, alerts_from_counts(est, g.umbral_brote_casos.to_numpy(float),
                                                         MIN_OUTBREAK_CASES), score=est - limit)
            row.update({f"{k}_estacional": m[k] for k in ("precision", "recall", "f1", "auprc")})
            mae_p = count_metrics(g.casos_Dengue, g.persistencia)["mae"]
            row["razon_mae_estacional"] = (count_metrics(g.casos_Dengue, est)["mae"] / mae_p
                                            if mae_p else None)
        if "casos_predichos" in g:
            mc = count_metrics(g.casos_Dengue, g.casos_predichos)
            mp = count_metrics(g.casos_Dengue, g.persistencia)
            row.update({"mae": mc["mae"], "rmse": mc["rmse"], "mae_persistencia": mp["mae"],
                         "rmse_persistencia": mp["rmse"],
                         "razon_mae": mc["mae"] / mp["mae"] if mp["mae"] else None,
                         "razon_rmse": mc["rmse"] / mp["rmse"] if mp["rmse"] else None})
        rows.append(row)
    return pd.DataFrame(rows)


def reliability_by_block(data: pd.DataFrame, n_bins: int = 10) -> pd.DataFrame:
    """Reliability curve of the calibrated probability per block and pooled 2022-2023."""
    parts = []
    evaluable = data[data.probabilidad_calibrada.notna()]
    for (h, block), g in evaluable.groupby(["horizonte", "bloque"]):
        parts.append(diag.reliability_curve(g.brote, g.probabilidad_calibrada, n_bins)
                      .reset_index(names="bin").assign(horizonte=h, bloque=block))
    for h, g in evaluable[evaluable.bloque.isin(SELECTION_BLOCKS)].groupby("horizonte"):
        parts.append(diag.reliability_curve(g.brote, g.probabilidad_calibrada, n_bins)
                      .reset_index(names="bin").assign(horizonte=h, bloque="seleccion_2022_2023"))
    return pd.concat(parts, ignore_index=True)


# ---------------------------------------------------------------------------
# Lead time on clean onsets
# ---------------------------------------------------------------------------

def clean_lead_time(data: pd.DataFrame, labels: pd.DataFrame, alerts: list[str]) -> pd.DataFrame:
    """Lead time per episode with a clean onset in the blocks with a calibrated alert."""
    evaluable = data[data.bloque.ne(INITIAL_CALIBRATION_BLOCK)
                       & data.bloque.ne(COUNT_SENSITIVITY_BLOCK)]
    table = diag.episode_lead_time(evaluable, labels, alerts)
    return table[table.semanas_previas_sin_brote >= diag.NO_PREVIOUS_OUTBREAK].reset_index(drop=True)


def _warned(table: pd.DataFrame, alert: str) -> np.ndarray:
    return table[alert].ge(MIN_LEAD_TIME).to_numpy(float)


def stratified_bootstrap(values: np.ndarray, strata: np.ndarray, n: int = N_BOOTSTRAP,
                            seed: int = BOOTSTRAP_SEED) -> np.ndarray:
    """Bootstrap means resampling episodes inside each stratum (season)."""
    rng = np.random.default_rng(seed)
    groups = [np.flatnonzero(strata == e) for e in np.unique(strata)]
    means = np.empty(n)
    for i in range(n):
        idx = np.concatenate([rng.choice(g, size=len(g), replace=True) for g in groups])
        means[i] = values[idx].mean()
    return means


def lead_time_ci_summary(table: pd.DataFrame, alert: str) -> pd.DataFrame:
    """Share of clean onsets warned >= 2 weeks ahead, with a bootstrap 95 % CI."""
    rows = []
    for h, g in table.groupby("horizonte"):
        sets = [(b, g[g.bloque.eq(b)]) for b in sorted(g.bloque.unique())]
        selection = g[g.bloque.isin(SELECTION_BLOCKS)]
        sets.append(("seleccion_2022_2023", selection))
        for name, t in sets:
            if t.empty:
                continue
            v = _warned(t, alert)
            means = stratified_bootstrap(v, t.bloque.to_numpy())
            rows.append({"horizonte": h, "bloque": name, "alerta": alert, "episodios": len(t),
                          "avisados_2_o_mas": float(v.mean()),
                          "ic95_inferior": float(np.quantile(means, 0.025)),
                          "ic95_superior": float(np.quantile(means, 0.975))})
    return pd.DataFrame(rows)


def lead_time_difference(table_a: pd.DataFrame, table_b: pd.DataFrame, alert_a: str,
                          alert_b: str | None = None) -> pd.DataFrame:
    """Paired A - B difference per episode in 2022-2023, with a bootstrap 95 % CI.

    Episodes depend only on the labels, so A and B share exactly the same set
    for a given horizon.
    """
    alert_b = alert_b or alert_a
    key = ["horizonte", "bloque", "ubigeo", "inicio"]
    a = table_a[table_a.bloque.isin(SELECTION_BLOCKS)]
    b = table_b[table_b.bloque.isin(SELECTION_BLOCKS)]
    pairs = a[key + [alert_a]].merge(b[key + [alert_b]], on=key, suffixes=("_a", "_b"),
                                        validate="one_to_one")
    if len(pairs) != len(a) or len(pairs) != len(b):
        raise ValueError("Las arquitecturas no comparten los mismos episodios")
    col_a = f"{alert_a}_a" if alert_a == alert_b else alert_a
    col_b = f"{alert_b}_b" if alert_a == alert_b else alert_b
    rows = []
    for h, g in pairs.groupby("horizonte"):
        diff = g[col_a].ge(MIN_LEAD_TIME).to_numpy(float) - g[col_b].ge(MIN_LEAD_TIME).to_numpy(float)
        means = stratified_bootstrap(diff, g.bloque.to_numpy())
        by_season = {b: float(diff[g.bloque.eq(b).to_numpy()].mean()) for b in SELECTION_BLOCKS}
        rows.append({"horizonte": h, "episodios": len(g), "diferencia": float(diff.mean()),
                      "ic95_inferior": float(np.quantile(means, 0.025)),
                      "ic95_superior": float(np.quantile(means, 0.975)),
                      **{f"diferencia_{b}": v for b, v in by_season.items()}})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Full evaluation, seed ranges and decision rule
# ---------------------------------------------------------------------------

def evaluate(pred: pd.DataFrame, labels: pd.DataFrame, method: str = CALIBRATION_METHOD) -> dict:
    """Apply the whole protocol to a set of predictions."""
    data, calibration = calibrate_chronologically(pred, method)
    data = add_protocol_alerts(data)
    alerts = ["alerta_050", "alerta_persistencia"] + (["alerta_regresion"] if "alerta_regresion" in data else [])
    lead_time = clean_lead_time(data, labels, alerts)
    result = {
        "datos": data, "calibracion": calibration,
        "metricas": metrics_by_block(data),
        "fiabilidad": reliability_by_block(data),
        "antelacion": lead_time,
        "antelacion_ic": pd.concat([lead_time_ci_summary(lead_time, a) for a in alerts], ignore_index=True),
    }
    if "casos_predichos" in data:
        data = data.assign(fase=diag.curve_phase(data))
        result["errores_por_fase"] = diag.error_breakdown(data, ["horizonte", "bloque", "fase"])
    return result


def seed_ranges(metrics: list[pd.DataFrame]) -> pd.DataFrame:
    """Range (maximum - minimum) across seeds per horizon, block and metric."""
    columns = list(DIRECTION) + ["rmse", "mae", "recall_050", "precision_050"]
    every = pd.concat(metrics, ignore_index=True)
    columns = [c for c in columns if c in every]
    grouped = every.groupby(["horizonte", "bloque"])[columns]
    return (grouped.max() - grouped.min()).reset_index()


def tie_threshold(*ranges: pd.DataFrame, horizons: tuple[int, ...] = (2, 3, 4)) -> pd.DataFrame:
    """Tie threshold: the largest range among the compared architectures.

    A horizon without its own ranges (h=3 before it was measured) takes the
    largest range of the horizons available in the same block.
    """
    all_items = pd.concat(ranges, ignore_index=True)
    by_h = all_items.groupby(["horizonte", "bloque"]).max().reset_index()
    worst = all_items.drop(columns="horizonte").groupby("bloque").max().reset_index()
    missing = [h for h in horizons if h not in set(by_h.horizonte)]
    extra = [worst.assign(horizonte=h) for h in missing]
    return pd.concat([by_h, *extra], ignore_index=True)[by_h.columns]


def decide(candidate: pd.DataFrame, reference: pd.DataFrame, ranges: pd.DataFrame,
            lead_time_diff: pd.DataFrame) -> pd.DataFrame:
    """Preregistered, symmetric verdict per horizon: wins, loses, offsets or ties.

    ``candidate`` (A) and ``reference`` (B) are metrics per block (seed median);
    ``ranges`` the tie threshold per metric; ``lead_time_diff`` the paired
    A - B lead-time difference. Improving and worsening require both selection
    seasons; the guards only veto a win. By construction, A loses against B if
    and only if B wins against A.
    """
    rows = []
    for h in sorted(candidate.horizonte.unique()):
        c = candidate[candidate.horizonte.eq(h)].set_index("bloque")
        r = reference[reference.horizonte.eq(h)].set_index("bloque")
        e = ranges[ranges.horizonte.eq(h)].set_index("bloque")
        delta = {m: {b: DIRECTION[m] * (c.at[b, m] - r.at[b, m]) for b in SELECTION_BLOCKS}
                 for m in DIRECTION if m in c and m in r}
        improves = {m: all(delta[m][b] > e.at[b, m] for b in SELECTION_BLOCKS) for m in delta}
        worsens = {m: all(delta[m][b] < -e.at[b, m] for b in SELECTION_BLOCKS) for m in delta}
        a = lead_time_diff[lead_time_diff.horizonte.eq(h)].iloc[0]
        improves_lead = bool(a.ic95_inferior > 0 and all(a[f"diferencia_{b}"] > 0 for b in SELECTION_BLOCKS))
        worsens_lead = bool(a.ic95_superior < 0 and all(a[f"diferencia_{b}"] < 0 for b in SELECTION_BLOCKS))
        improves_primary = any(improves.get(m, False) for m in PRIMARY) or improves_lead
        worsens_primary = any(worsens.get(m, False) for m in PRIMARY) or worsens_lead
        veto_a = [m for m in GUARDS if worsens.get(m, False)]
        veto_b = [m for m in GUARDS if improves.get(m, False)]
        if improves_primary and not worsens_primary and not veto_a:
            verdict = "gana"
        elif worsens_primary and not improves_primary and not veto_b:
            verdict = "pierde"
        elif improves_primary or worsens_primary:
            verdict = "compensa (empate)"
        else:
            verdict = "empate"
        rows.append({"horizonte": h, "veredicto": verdict,
                      "mejora_f1_050": improves.get("f1_050"), "empeora_f1_050": worsens.get("f1_050"),
                      "mejora_antelacion": improves_lead, "empeora_antelacion": worsens_lead,
                      "vetos": ", ".join(veto_a) or None, "vetos_contra_referencia": ", ".join(veto_b) or None,
                      **{f"umbral_{m}_{b}": e.at[b, m] for m in delta for b in SELECTION_BLOCKS},
                      **{f"delta_{m}_{b}": DIRECTION[m] * v for m, d in delta.items() for b, v in d.items()}})
    return pd.DataFrame(rows)


def seed_median(metrics: list[pd.DataFrame]) -> pd.DataFrame:
    """Median of each metric across seeds, per horizon and block."""
    every = pd.concat(metrics, ignore_index=True)
    numeric = every.select_dtypes("number").columns.difference(["horizonte"])
    return every.groupby(["horizonte", "bloque"])[list(numeric)].median().reset_index()


def from_compact(predictions: pd.DataFrame) -> pd.DataFrame:
    """Convert ``predicciones_por_bloque.csv`` of experiment 30 to the standard format (E1)."""
    common = [*KEY, "semana_inicio", "origen_cierre", "horizonte", "bloque",
               "casos_Dengue", "brote", "umbral_brote_casos"]
    reg = predictions[predictions.variante.eq(diag.REGRESSION_VARIANT)].copy()
    cls = predictions[predictions.variante.eq(diag.CLASSIFICATION_VARIANT)]
    reg["persistencia"] = np.where(reg.horizonte.eq(2), reg.casos_lag_2, reg.casos_lag_4)
    data = reg[common + ["casos_predichos", "persistencia"]].merge(
        cls[common + ["probabilidad_brote"]], on=common, validate="one_to_one")
    if len(data) != len(reg) or len(data) != len(cls):
        raise ValueError("Regresión y clasificación no cubren las mismas filas")
    return validate_predictions(data)
