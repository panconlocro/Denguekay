"""Phase 2: calibration variants over L (trained from 2005), with the five-season protocol.

Calibration does not retrain anything: every variant recalibrates the saved uncalibrated predictions of L
(``models/experimentos/mejora_modelo/fase1a/predicciones_L.csv.gz``, 5 seeds). μ does not change, so the
count metrics are the same in every variant.

``calibrate_variant`` generalises ``protocol.calibrate_chronologically`` (same blocks, same cut-off, same
closed labels): with ``method="platt"``, ``eps=1e-6`` and ``pooled=False`` it must reproduce it bit for bit
(guard G5).
"""

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from denguekay.config.paths import MODELS
from denguekay.evaluation import protocol as pa
from denguekay.evaluation.metrics import select_f1_threshold

EPS_REFERENCE = pa.EPS            # 1e-6, the clip of the V1/V2 and of L
EPS_SMALL = 1e-15                 # smallest eps with 1 - eps distinguishable from 1 in float64
ISOTONIC_MIN_POSITIVES = 500      # below it the block falls back to Platt (antecedent S5: 71-84 positives)
LOG_LOSS_EPS = 1e-15              # clip of the log-loss metric only (never of a calibrator)
L_SAVED = MODELS / "experimentos" / "mejora_modelo" / "fase1a" / "predicciones_L.csv.gz"
OUTPUT_DIR = MODELS / "experimentos" / "mejora_modelo" / "fase2"


# ---------------------------------------------------------------------------
# Calibrators: each returns (function p -> calibrated p, parameters)
# ---------------------------------------------------------------------------

def logit(p, eps: float) -> np.ndarray:
    p = np.clip(np.asarray(p, float), eps, 1 - eps)
    return np.log(p / (1 - p))


def _logistic(x: np.ndarray, y: np.ndarray) -> LogisticRegression:
    return LogisticRegression(C=1e6, max_iter=1000).fit(x, np.asarray(y, int))


def fit_platt(p, y, eps: float = EPS_REFERENCE):
    """Platt on the clipped logit, with the same estimator as ``protocol.fit_platt``."""
    model = _logistic(logit(p, eps).reshape(-1, 1), y)
    params = {"a": float(model.coef_[0, 0]), "c": float(model.intercept_[0])}
    return (lambda q: model.predict_proba(logit(q, eps).reshape(-1, 1))[:, 1]), params


def _beta_features(p, eps: float) -> np.ndarray:
    p = np.clip(np.asarray(p, float), eps, 1 - eps)
    return np.column_stack([np.log(p), -np.log(1 - p)])


def fit_beta(p, y, eps: float = EPS_REFERENCE):
    """Beta calibration (Kull, Silva Filho and Flach, AISTATS 2017): logistic on [ln p, -ln(1 - p)].

    Three parameters (a, b, c); with a = b it is Platt. Monotone by construction of this study: a term
    with a negative coefficient is dropped and the rest refitted (the most negative first); if no term is
    left, the block falls back to Platt with the same eps.
    """
    x = _beta_features(p, eps)
    keep = [0, 1]
    while keep:
        model = _logistic(x[:, keep], y)
        coef = model.coef_[0]
        if (coef >= 0).all():
            full = np.zeros(2)
            full[keep] = coef
            params = {"a": float(full[0]), "b": float(full[1]), "c": float(model.intercept_[0]),
                      "terminos": len(keep), "respaldo": None}
            cols = list(keep)
            return (lambda q: model.predict_proba(_beta_features(q, eps)[:, cols])[:, 1]), params
        keep.pop(int(np.argmin(coef)))
    f, params = fit_platt(p, y, eps)
    return f, {**params, "respaldo": "platt"}


def fit_isotonic(p, y, eps: float = EPS_REFERENCE):
    """Isotonic regression on the raw probability; fewer positives than the minimum -> Platt."""
    y = np.asarray(y, int)
    if y.sum() < ISOTONIC_MIN_POSITIVES:
        f, params = fit_platt(p, y, eps)
        return f, {**params, "respaldo": "platt"}
    model = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(np.asarray(p, float), y)
    return (lambda q: model.predict(np.asarray(q, float))), {"escalones": int(len(model.X_thresholds_)),
                                                              "respaldo": None}


CALIBRATORS = {"platt": fit_platt, "beta": fit_beta, "isotonica": fit_isotonic}


# ---------------------------------------------------------------------------
# Chronological calibration of a variant
# ---------------------------------------------------------------------------

def _available(by_h: pd.DataFrame, onsets: pd.Series, block: str, cutoff: pd.Timestamp) -> pd.DataFrame:
    previous = by_h[by_h.bloque.map(onsets).lt(onsets[block])]
    return previous[(previous.semana_inicio + pd.Timedelta(days=6)).le(cutoff)]


def calibrate_variant(pred: pd.DataFrame, method: str = "platt", eps: float = EPS_REFERENCE,
                      pooled: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``probabilidad_calibrada`` and ``umbral_diagnostico_f1`` per horizon and block, like the protocol.

    Per horizon (``pooled=False``) the calibrator of a block uses the rows of that horizon from earlier
    blocks whose label closed by the block's first origin. Pooled, one calibrator per block uses the rows
    of the three horizons whose label closed by the earliest of the three first origins, and is applied
    to every horizon. The diagnostic F1 threshold is always computed per horizon (it does not decide).
    """
    fit = CALIBRATORS[method]
    data = pa.validate_predictions(pred)
    data["probabilidad_calibrada"] = np.nan
    data["umbral_diagnostico_f1"] = np.nan
    horizons = {h: g for h, g in data.groupby("horizonte")}
    onsets = {h: g.groupby("bloque").semana_inicio.min().sort_values() for h, g in horizons.items()}
    cutoffs = {(h, b): pa.block_cutoff(g[g.bloque.eq(b)]) for h, g in horizons.items() for b in onsets[h].index}
    record = []
    for h, by_h in horizons.items():
        for block in onsets[h].index:
            idx = by_h.index[by_h.bloque.eq(block)]
            own = _available(by_h, onsets[h], block, cutoffs[(h, block)])
            if pooled:
                cut = min(cutoffs[(k, block)] for k in horizons if (k, block) in cutoffs)
                fit_rows = pd.concat([_available(g, onsets[k], block, cut) for k, g in horizons.items()
                                      if block in onsets[k].index])
            else:
                cut, fit_rows = cutoffs[(h, block)], own
            row = {"horizonte": h, "bloque": block, "corte": cut, "metodo": method, "eps": eps,
                   "agrupado": pooled, "filas_calibracion": len(fit_rows),
                   "positivos_calibracion": int(fit_rows.brote.sum())}
            if fit_rows.brote.nunique() == 2 and own.brote.nunique() == 2:
                calibrate, params = fit(fit_rows.probabilidad_brote.to_numpy(float), fit_rows.brote.to_numpy(int),
                                        eps)
                data.loc[idx, "probabilidad_calibrada"] = calibrate(data.loc[idx, "probabilidad_brote"])
                diagnosis = select_f1_threshold(own.brote.to_numpy(int), calibrate(own.probabilidad_brote))
                data.loc[idx, "umbral_diagnostico_f1"] = diagnosis["umbral"]
                row.update(params)
            record.append(row)
    return data, pd.DataFrame(record)


# ---------------------------------------------------------------------------
# Evaluation, guards and readings
# ---------------------------------------------------------------------------

def log_loss_by_block(data: pd.DataFrame) -> pd.DataFrame:
    """Calibrated and uncalibrated log-loss per horizon and block (probabilities clipped to 1e-15)."""
    rows = []
    for (h, block), g in data[data.probabilidad_calibrada.notna()].groupby(["horizonte", "bloque"]):
        y = g.brote.to_numpy(float)
        out = {"horizonte": h, "bloque": block}
        for name, col in (("log_loss", "probabilidad_calibrada"), ("log_loss_sin_calibrar", "probabilidad_brote")):
            p = np.clip(g[col].to_numpy(float), LOG_LOSS_EPS, 1 - LOG_LOSS_EPS)
            out[name] = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
        rows.append(out)
    return pd.DataFrame(rows)


def evaluate_calibrated(data: pd.DataFrame, labels: pd.DataFrame) -> dict:
    """``protocol.evaluate`` after an already calibrated table (plus the log-loss)."""
    data = pa.add_protocol_alerts(data)
    alerts = ["alerta_050", "alerta_persistencia", "alerta_regresion"]
    lead = pa.clean_lead_time(data, labels, alerts)
    metrics = pa.metrics_by_block(data).merge(log_loss_by_block(data), on=["horizonte", "bloque"], how="left")
    return {"datos": data, "metricas": metrics, "fiabilidad": pa.reliability_by_block(data), "antelacion": lead,
            "antelacion_ic": pd.concat([pa.lead_time_ci_summary(lead, a) for a in alerts], ignore_index=True)}


def run_variant(preds: dict[int, pd.DataFrame], labels: pd.DataFrame, method: str, eps: float,
                pooled: bool = False) -> dict:
    """Calibrate and evaluate the five seeds of L with one variant."""
    evals, records = {}, []
    for seed, pred in preds.items():
        data, record = calibrate_variant(pred, method, eps, pooled)
        evals[seed] = evaluate_calibrated(data, labels)
        records.append(record.assign(semilla=seed))
    return {"evaluaciones": evals, "calibradores": pd.concat(records, ignore_index=True)}


def reproduces_protocol(pred: pd.DataFrame) -> dict:
    """G5: Platt per horizon with eps 1e-6 equals ``protocol.calibrate_chronologically`` bit for bit."""
    ours, _ = calibrate_variant(pred, "platt", EPS_REFERENCE, pooled=False)
    theirs, _ = pa.calibrate_chronologically(pred, "platt")
    a, b = ours.probabilidad_calibrada.to_numpy(float), theirs.probabilidad_calibrada.to_numpy(float)
    same_nan = bool((np.isnan(a) == np.isnan(b)).all())
    diff = float(np.nanmax(np.abs(a - b))) if same_nan else float("inf")
    return {"pasa": same_nan and diff == 0.0, "diferencia_maxima": diff}


def monotone_violations(data: pd.DataFrame) -> int:
    """G6: horizon-blocks where the calibrated probability is not a non-decreasing function of the raw one."""
    bad = 0
    for _, g in data[data.probabilidad_calibrada.notna()].groupby(["horizonte", "bloque"]):
        s = g.sort_values(["probabilidad_brote", "probabilidad_calibrada"])
        bad += int((np.diff(s.probabilidad_calibrada.to_numpy(float)) < -1e-12).any())
    return bad


def calibration_guard(evals: dict[int, dict], blocks: list[str]) -> pd.DataFrame:
    """Per horizon: seasons where the calibrated Brier or log-loss is worse than the uncalibrated in all seeds."""
    every = pd.concat({s: e["metricas"] for s, e in evals.items()}, names=["semilla"]).reset_index(level=0)
    every = every[every.bloque.isin(blocks)]
    every["peor_brier"] = every.brier > every.brier_sin_calibrar
    every["peor_log_loss"] = every.log_loss > every.log_loss_sin_calibrar
    by = every.groupby(["horizonte", "bloque"])[["peor_brier", "peor_log_loss"]].all()
    by["en_contra"] = by.peor_brier | by.peor_log_loss
    return by.reset_index()


def read_l_predictions() -> dict[int, pd.DataFrame]:
    saved = pd.read_csv(L_SAVED, dtype={"ubigeo": "string"}, float_precision="round_trip")
    saved["ubigeo"] = saved.ubigeo.astype(object)
    return {int(s): g.drop(columns="semilla").reset_index(drop=True) for s, g in saved.groupby("semilla")}
