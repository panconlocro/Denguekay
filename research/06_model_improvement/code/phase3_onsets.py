"""Phase 3: outbreak onsets over L (trained from 2005, Platt per horizon with clip 1e-6).

Variants, one at a time against L (``preregistration.PHASE3``):

- 3a1 sample weights on onset targets; 3a2 sample weights per season;
- 3b two regimes (district without / with outbreak at the origin), combined by the state at the origin;
- 3c B1 + B2 only in the onset regime of 3b.

``predict_blocks_weighted`` is ``phase1_history.predict_blocks`` with optional weights and regimes; with
neither it follows the same path (guard G8 checks it reproduces the saved L predictions).
"""

import numpy as np
import pandas as pd

from denguekay.config.paths import MODELS
from denguekay.evaluation import episodes as diag
from denguekay.model import horizon_strategies as eh
from denguekay.model import probabilistic_output as sp
from denguekay.model.train import SEASON_START_WEEK

ONSET_WEEKS = 2                  # "brote nuevo": first 2 weeks of an episode with a clean onset
ONSET_WEIGHT = 5.0               # 3a1, fixed a priori (one value, no grid)
SEASON_WEIGHT_CLIP = (0.25, 1.0)  # 3a2: no season weighs more than today (Rosa)
MIN_REGIME_ROWS = 100            # 3b: fewer training origins in a regime -> that block uses the single model
FORMULATION = "S4_s3"
OUTPUT_DIR = MODELS / "experimentos" / "mejora_modelo" / "fase3"
H = eh.STRATEGY_HORIZONS


# ---------------------------------------------------------------------------
# Weights (computed inside each block with its training origins only)
# ---------------------------------------------------------------------------

def onset_weeks(series: pd.DataFrame, weeks: int = ONSET_WEEKS) -> set[tuple[str, pd.Timestamp]]:
    """(ubigeo, week) of the outbreak weeks that open an episode with a clean onset, as in
    ``probabilistic_output.recall_by_week_type``. An episode start only depends on earlier labels."""
    eps = diag.episodes(series)
    clean = eps[eps.semanas_previas_sin_brote >= diag.NO_PREVIOUS_OUTBREAK]
    brote = set(zip(series.loc[series.brote.eq(1), "ubigeo"], pd.to_datetime(series.loc[series.brote.eq(1),
                                                                                            "semana_inicio"])))
    out = set()
    for ep in clean.itertuples(index=False):
        for k in range(weeks):
            key = (ep.ubigeo, ep.inicio + pd.Timedelta(weeks=k))
            if key in brote:
                out.add(key)
    return out


def onset_weights(train: pd.DataFrame, new_weeks: set, factor: float = ONSET_WEIGHT) -> np.ndarray:
    """``factor`` for the origins with at least one of their three targets in ``new_weeks``, 1 otherwise."""
    hit = np.zeros(len(train), bool)
    for h in H:
        hit |= np.fromiter(((u, w) in new_weeks for u, w in zip(train.ubigeo, train[f"semana_inicio_h{h}"])),
                           bool, len(train))
    return np.where(hit, factor, 1.0)


def target_season(weeks: pd.Series) -> np.ndarray:
    """Epidemiological season (week 35 to 34) of a target week, labelled by the year it ends."""
    from denguekay.data.calendar import mmwr_epi_week

    cal = mmwr_epi_week(pd.Series(pd.to_datetime(weeks).to_numpy()))
    return (cal.anio_epi + cal.semana_epi.ge(SEASON_START_WEEK).astype(int)).to_numpy()


def season_weights(train: pd.DataFrame, clip: tuple[float, float] = SEASON_WEIGHT_CLIP) -> np.ndarray:
    """Per season s of the h=2 target: median_s(C) / C_s clipped, with C_s the h=2 target cases of the
    block's training origins in s (0 cases -> the upper clip). Heavy seasons (2017, 2023) weigh less; none weighs more than 1."""
    season = target_season(train[f"semana_inicio_h{H[0]}"])
    totals = pd.Series(train[f"casos_Dengue_h{H[0]}"].to_numpy(float)).groupby(season).sum()
    med = float(totals.median())
    ratio = {s: (med / c if c > 0 else np.inf) for s, c in totals.items()}
    return np.clip(np.array([ratio[s] for s in season]), *clip)


# ---------------------------------------------------------------------------
# State at the origin (known when the origin week closes)
# ---------------------------------------------------------------------------

def origin_state(origins: pd.DataFrame, series: pd.DataFrame) -> np.ndarray:
    """``brote`` of the origin week (the week that closes at ``origen_cierre``); its label uses the same
    week of previous years and the cases of that week, so it is known at the origin. Missing -> 0."""
    week = pd.to_datetime(origins.origen_cierre) - pd.Timedelta(days=6)
    lab = series[["ubigeo", "semana_inicio", "brote"]].assign(semana_inicio=lambda d: pd.to_datetime(d.semana_inicio))
    key = pd.DataFrame({"ubigeo": origins.ubigeo.astype(str).to_numpy(), "semana_inicio": week.to_numpy()})
    joined = key.merge(lab.assign(ubigeo=lab.ubigeo.astype(str)), on=["ubigeo", "semana_inicio"], how="left",
                       validate="many_to_one")
    return joined.brote.fillna(0).astype(int).to_numpy()


# ---------------------------------------------------------------------------
# Block loop with weights and regimes
# ---------------------------------------------------------------------------

def _training(origins: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    complete = origins.dropna(subset=[f"semana_inicio_h{h}" for h in H])
    sel = (complete[f"semana_inicio_h{H[-1]}"] + pd.Timedelta(days=6)).le(cutoff)
    train = complete[sel]
    if train.empty or not train.origen_cierre.lt(train.semana_inicio).all():
        raise ValueError("Entrenamiento multi-salida vacío o con fuga")
    return train


def _fit(train: pd.DataFrame, seed: int, col_reg: list[str], extra: dict, margin_all: np.ndarray,
         weights: np.ndarray | None):
    """The S4_s3 regressor of ``sp.fit_e3`` with an optional ``sample_weight``; α unweighted, in-sample."""
    f = sp.FORMULATIONS[FORMULATION]
    m_tr = margin_all[train.index]
    y = np.column_stack([train[f"casos_Dengue_h{h}"] for h in H])
    if weights is None:
        reg = sp.fit_count(train[col_reg], y, f["conteo"], seed, m_tr, **extra)
    else:
        from xgboost import XGBRegressor

        reg = XGBRegressor(**sp.count_objective(f["conteo"]), **eh.parameters(seed, **extra))
        reg.fit(train[col_reg], np.asarray(y, float), base_margin=m_tr, sample_weight=weights)
    fit = sp.predict_count(reg, train[col_reg], f["conteo"], m_tr)
    alphas = [sp.negative_binomial_dispersion(fit[:, i], y[:, i]) for i in range(len(H))]
    return reg, alphas


def predict_blocks_weighted(matrices: dict[int, pd.DataFrame], origins: pd.DataFrame,
                            blocks: list[tuple[str, str, int]], seed: int, columns: list[str],
                            hyperparameters: dict, weights_fn=None, state: np.ndarray | None = None,
                            onset_columns: list[str] | None = None, prepare_block=None) -> pd.DataFrame:
    """E3 · S4_s3 OOS predictions per block, like ``phase1_history.predict_blocks``.

    ``weights_fn(train) -> weights`` (3a). ``state`` (3b): 0/1 per origin; one model per state, each
    trained with the training origins of its state, predicting the origins of its state. A state with
    fewer than ``MIN_REGIME_ROWS`` training origins in a block falls back to the single model there.
    ``onset_columns`` (3c): extra columns of the state-0 model; ``prepare_block(origins, cutoff)`` adds
    the columns fitted per block (B2).
    """
    f = sp.FORMULATIONS[FORMULATION]
    col_reg = list(columns)
    extra = sp.e3_parameters(hyperparameters)
    margin_all = sp.e3_margin(origins, FORMULATION)
    parts, record = [], []
    for block, kind, period in blocks:
        test_sets, cutoff = eh._common_cutoffs(matrices, kind, period)
        o = prepare_block(origins, cutoff) if prepare_block is not None else origins
        train = _training(o, cutoff)
        counts = np.full((len(o), len(H)), np.nan)
        alpha_rows = np.full((len(o), len(H)), np.nan)
        groups = [(None, np.ones(len(o), bool), col_reg)]
        if state is not None:
            groups = [(s, state == s, col_reg + (list(onset_columns or []) if s == 0 else [])) for s in (0, 1)]
        for s, mask, cols in groups:
            sub = train[mask[train.index]] if s is not None else train
            fallback = s is not None and len(sub) < MIN_REGIME_ROWS
            use, use_cols = (train, col_reg) if fallback else (sub, cols)
            w = weights_fn(use) if weights_fn is not None else None
            reg, alphas = _fit(use, seed, use_cols, extra, margin_all, w)
            idx = np.flatnonzero(mask)
            counts[idx] = sp.predict_count(reg, o.iloc[idx][use_cols], f["conteo"], margin_all[idx])
            alpha_rows[idx] = alphas
            record.append({"bloque": block, "regimen": s, "filas_entrenamiento": len(use), "respaldo": fallback,
                           **{f"alpha_h{h}": a for h, a in zip(H, alphas)}, "corte": cutoff})
        for step, h in enumerate(H):
            pred = pd.DataFrame({"ubigeo": o.ubigeo, "semana_inicio": o[f"semana_inicio_h{h}"],
                                 "origen_cierre_mimo": o.origen_cierre, "casos_predichos": counts[:, step],
                                 "alpha": alpha_rows[:, step]})
            test = test_sets[h].merge(pred.dropna(subset=["semana_inicio"]), on=["ubigeo", "semana_inicio"],
                                      how="left", validate="one_to_one")
            if test.casos_predichos.isna().any() or not test.origen_cierre_mimo.eq(test.origen_cierre).all():
                raise ValueError(f"Predicciones incompletas o con origen distinto en {block} h={h}")
            prob = np.empty(len(test))
            for a in np.unique(test.alpha):
                m = test.alpha.eq(a).to_numpy()
                prob[m] = sp.negative_binomial_probability(test.casos_predichos[m], a, test.umbral_brote_casos[m])
            test["probabilidad_brote"] = prob
            parts.append(eh._output(test, block, test.casos_predichos, test.probabilidad_brote))
    output = pd.concat(parts, ignore_index=True).assign(estrategia="E3", formulacion=FORMULATION, semilla=seed)
    output.attrs["ajustes"] = pd.DataFrame(record)
    return output
