"""Phase 6: baselines of another family on the matrix and protocol of L (reading, does not decide).

Families (``preregistration.PHASE6``), each with the C3 columns, the long origins since 2005, the seasonal
blocks of L and the same training cut-off (``phase3_onsets._training``):

- 6a NB2 GLM per horizon (statsmodels), offset log(hist_lag_a + 0.5) = the S4_s3 margin, standardised
  columns (log1p for the case levels), no penalty;
- 6b LightGBM Poisson per horizon (no multi-output trees), init_score = the S4_s3 margin, the V1
  hyperparameters translated.

The probability is NB2 with the in-sample alpha (L's estimator) for every family, then the protocol
(Platt per horizon, 1e-6). ``columns`` is a parameter so that 6' (C3 + climate lags) reuses this code.
"""

import numpy as np
import pandas as pd

from denguekay.config.paths import MODELS
from denguekay.evaluation import protocol as pa
from denguekay.model import horizon_strategies as eh
from denguekay.model import probabilistic_output as sp

H = eh.STRATEGY_HORIZONS
OUTPUT_DIR = MODELS / "experimentos" / "mejora_modelo" / "fase6"
FAMILIES = ("6a_nb_glm", "6b_lightgbm")


# ---------------------------------------------------------------------------
# 6a · NB2 GLM
# ---------------------------------------------------------------------------

def _glm_design(x: pd.DataFrame, center: pd.Series, scale: pd.Series, log1p: tuple[str, ...]) -> np.ndarray:
    z = x.astype(float).copy()
    for c in log1p:
        if c in z:
            z[c] = np.log1p(z[c])
    z = (z - center) / scale
    return np.column_stack([np.ones(len(z)), z.to_numpy()])


def fit_glm(train: pd.DataFrame, columns: list[str], margin: np.ndarray, seed: int) -> dict:
    """One NB2 GLM per horizon; standardisation with the block's training only. ``seed`` is unused."""
    import warnings

    from statsmodels.discrete.discrete_model import NegativeBinomial

    import preregistration as pr

    log1p = tuple(c for c in pr.PHASE6_GLM_LOG1P if c in columns)
    raw = train[columns].astype(float).copy()
    for c in log1p:
        raw[c] = np.log1p(raw[c])
    center, scale = raw.mean(), raw.std(ddof=0).replace(0.0, 1.0)
    X = _glm_design(train[columns], center, scale, log1p)
    models, converged = [], []
    for step, h in enumerate(H):
        y = train[f"casos_Dengue_h{h}"].to_numpy(float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = NegativeBinomial(y, X, offset=margin[:, step], loglike_method="nb2").fit(
                maxiter=pr.PHASE6_GLM_MAXITER, disp=0)
        models.append(res.params[:-1])          # the last parameter is the GLM's own alpha
        converged.append(bool(res.mle_retvals.get("converged", False)))
    return {"beta": models, "center": center, "scale": scale, "log1p": log1p, "columns": columns,
            "convergio": converged}


def predict_glm(fitted: dict, origins: pd.DataFrame, margin: np.ndarray) -> np.ndarray:
    X = _glm_design(origins[fitted["columns"]], fitted["center"], fitted["scale"], fitted["log1p"])
    out = np.column_stack([np.exp(X @ b + margin[:, step]) for step, b in enumerate(fitted["beta"])])
    if not np.isfinite(out).all():
        raise ValueError("El GLM produjo conteos no finitos")
    return out


# ---------------------------------------------------------------------------
# 6b · LightGBM Poisson
# ---------------------------------------------------------------------------

def _lgbm(seed: int, n_jobs: int):
    from lightgbm import LGBMRegressor

    import preregistration as pr

    return LGBMRegressor(objective="poisson", random_state=seed, deterministic=True, force_row_wise=True,
                         n_jobs=n_jobs, verbose=-1, **pr.PHASE6_LGBM)


def fit_lgbm(train: pd.DataFrame, columns: list[str], margin: np.ndarray, seed: int, n_jobs: int = 12) -> dict:
    models = []
    for step, h in enumerate(H):
        m = _lgbm(seed, n_jobs)
        m.fit(train[columns], train[f"casos_Dengue_h{h}"].to_numpy(float), init_score=np.ascontiguousarray(margin[:, step]))
        models.append(m)
    return {"modelos": models, "columns": columns}


def predict_lgbm(fitted: dict, origins: pd.DataFrame, margin: np.ndarray) -> np.ndarray:
    x = origins[fitted["columns"]]
    out = np.column_stack([np.exp(m.predict(x, raw_score=True) + margin[:, step])
                           for step, m in enumerate(fitted["modelos"])])
    if not np.isfinite(out).all():
        raise ValueError("LightGBM produjo conteos no finitos")
    return out


FIT = {"6a_nb_glm": (fit_glm, predict_glm), "6b_lightgbm": (fit_lgbm, predict_lgbm)}


# ---------------------------------------------------------------------------
# Block loop (same blocks, cut-offs and output as phase3_onsets.predict_blocks_weighted)
# ---------------------------------------------------------------------------

def predict_blocks_family(matrices: dict[int, pd.DataFrame], origins: pd.DataFrame,
                          blocks: list[tuple[str, str, int]], seed: int, columns: list[str],
                          family: str) -> pd.DataFrame:
    """OOS predictions per block of one family, with the NB2 probability from the in-sample alpha."""
    from phase3_onsets import FORMULATION, _training

    fit, predict = FIT[family]
    margin_all = sp.e3_margin(origins, FORMULATION)
    parts, record = [], []
    for block, kind, period in blocks:
        test_sets, cutoff = eh._common_cutoffs(matrices, kind, period)
        train = _training(origins, cutoff)
        fitted = fit(train, list(columns), margin_all[train.index], seed)
        in_sample = predict(fitted, train, margin_all[train.index])
        y = np.column_stack([train[f"casos_Dengue_h{h}"] for h in H])
        alphas = [sp.negative_binomial_dispersion(in_sample[:, i], y[:, i]) for i in range(len(H))]
        counts = predict(fitted, origins, margin_all)
        record.append({"bloque": block, "filas_entrenamiento": len(train), "corte": cutoff,
                       **{f"alpha_h{h}": a for h, a in zip(H, alphas)},
                       **({f"convergio_h{h}": c for h, c in zip(H, fitted["convergio"])}
                          if "convergio" in fitted else {})})
        for step, h in enumerate(H):
            pred = pd.DataFrame({"ubigeo": origins.ubigeo, "semana_inicio": origins[f"semana_inicio_h{h}"],
                                 "origen_cierre_mimo": origins.origen_cierre, "casos_predichos": counts[:, step]})
            test = test_sets[h].merge(pred.dropna(subset=["semana_inicio"]), on=["ubigeo", "semana_inicio"],
                                      how="left", validate="one_to_one")
            if test.casos_predichos.isna().any() or not test.origen_cierre_mimo.eq(test.origen_cierre).all():
                raise ValueError(f"Predicciones incompletas o con origen distinto en {block} h={h}")
            test["probabilidad_brote"] = sp.negative_binomial_probability(
                test.casos_predichos, alphas[step], test.umbral_brote_casos)
            parts.append(eh._output(test, block, test.casos_predichos, test.probabilidad_brote))
    output = pd.concat(parts, ignore_index=True).assign(estrategia=family, formulacion=FORMULATION, semilla=seed)
    output.attrs["ajustes"] = pd.DataFrame(record)
    return output


def run_family(inp: dict, family: str, seeds, columns: list[str] | None = None) -> dict:
    """Predictions and protocol evaluation of one family: raw μ and with the 5a mixture of the count.

    The GLM is deterministic: it runs once and the same predictions fill every seed key.
    """
    import phase1_history as p1
    from phase3_onsets import _config
    from phase5_counts import evaluate_mixture

    columns = list(columns if columns is not None else _config()[0])
    blocks = p1.seasonal_blocks(p1.FIRST_BLOCK_SEASON_LONG)
    preds, fits = {}, []
    for seed in seeds:
        if family == "6a_nb_glm" and preds:
            preds[seed] = next(iter(preds.values())).assign(semilla=seed)
            continue
        pred = predict_blocks_family(inp["matrices"], inp["origenes"], blocks, seed, columns, family)
        fits.append(pred.attrs.pop("ajustes").assign(semilla=seed))
        preds[seed] = pred
    raw = {s: pa.evaluate(p, inp["serie"]) for s, p in preds.items()}
    mixed = {s: evaluate_mixture(p, inp["serie"]) for s, p in preds.items()}
    return {"predicciones": preds, "evaluaciones": mixed, "evaluaciones_mu": raw,
            "ajustes": pd.concat(fits, ignore_index=True)}


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def guard_g14(fits: pd.DataFrame, l_alphas: pd.DataFrame) -> dict:
    """G14: training rows and cut-off of every block equal L's (alfas_L.csv, seed 17)."""
    ref = (l_alphas[l_alphas.semilla.eq(17)].drop_duplicates("bloque")
           .set_index("bloque")[["filas_entrenamiento", "corte"]])
    ref["corte"] = pd.to_datetime(ref.corte)
    ours = fits.drop_duplicates("bloque").set_index("bloque")[["filas_entrenamiento", "corte"]]
    ours["corte"] = pd.to_datetime(ours.corte)
    same_blocks = sorted(ours.index) == sorted(ref.index)
    diff = int((ours.reindex(ref.index) != ref).any(axis=1).sum()) if same_blocks else -1
    return {"mismos_bloques": same_blocks, "bloques_distintos": diff, "pasa": same_blocks and diff == 0}


def guard_g16_reproduction(evaluations: dict, saved_metrics: list[dict], tol: float = 1e-9) -> dict:
    """G16 (second part): L + 5a evaluated now reproduces the candidate metrics of 5a in fase5.json."""
    med = pa.seed_median([e["metricas"] for e in evaluations.values()]).set_index(["horizonte", "bloque"])
    saved = pd.DataFrame(saved_metrics).set_index(["horizonte", "bloque"])
    worst = 0.0
    for m in ("razon_mae", "razon_rmse", "f1_050", "auprc", "brier"):
        a = med.loc[saved.index, m].to_numpy(float)
        worst = max(worst, float(np.nanmax(np.abs(a - saved[f"{m}_cand"].to_numpy(float)))))
    return {"diferencia_maxima": worst, "filas": len(saved), "pasa": worst <= tol}


def l_plus_5a(series: pd.DataFrame) -> dict:
    """The base: L's saved predictions with the 5a mixture of the count."""
    import phase2_calibration as p2
    from phase5_counts import evaluate_mixture

    preds = p2.read_l_predictions()
    return {"predicciones": preds, "evaluaciones": {s: evaluate_mixture(p, series) for s, p in preds.items()}}
