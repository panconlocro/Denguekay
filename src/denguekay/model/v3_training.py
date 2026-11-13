"""Training of the V3 (``frozen_configs.CONFIG_V3``) on the long origins, and its 5a count mixture.

The same calls as study 06 (``phase3_onsets._training`` and ``_fit``, ``phase5_counts.fit_w``), so a fit at a
block's cutoff reproduces the study's predictions of that block bit for bit on the same device and threads:

- training rows: origins whose three targets exist and whose h=4 target closed at the cutoff;
- one ``count:poisson`` multi-output regressor with ``base_margin = log(cases of the origin + 0.5)``;
- α per horizon by maximum likelihood on the in-sample predictions (NB2);
- the published count ``w · μ + (1 − w) · persistence``, with ``w`` per horizon on a 0.01 grid (lowest MAE; ties
  go to the largest ``w``) fitted with earlier out-of-sample predictions whose label closed at the cutoff.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from denguekay.model import horizon_strategies as eh
from denguekay.model import probabilistic_output as sp

H = eh.STRATEGY_HORIZONS
FORMULATION = "S4_s3"
W_GRID = np.round(np.linspace(0, 1, 101), 2)


@dataclass
class Fit:
    regressor: object
    alphas: dict[int, float]
    train: pd.DataFrame


def training_rows(origins: pd.DataFrame, cutoff) -> pd.DataFrame:
    """Origins with the three targets whose h=4 target closed at ``cutoff`` (no leakage)."""
    complete = origins.dropna(subset=[f"semana_inicio_h{h}" for h in H])
    train = complete[(complete[f"semana_inicio_h{H[-1]}"] + pd.Timedelta(days=6)).le(pd.Timestamp(cutoff))]
    if train.empty or not train.origen_cierre.lt(train.semana_inicio).all():
        raise ValueError("Entrenamiento multi-salida vacío o con fuga")
    return train


def margin(origins: pd.DataFrame) -> np.ndarray:
    """``base_margin`` of every origin (positional: ``origins`` must have a RangeIndex)."""
    return sp.e3_margin(origins, FORMULATION)


def fit(origins: pd.DataFrame, cutoff, seed: int, columns: list[str], hyperparameters: dict) -> Fit:
    """The V3 regressor and its in-sample α at ``cutoff``."""
    f = sp.FORMULATIONS[FORMULATION]
    train = training_rows(origins, cutoff)
    m_tr = margin(origins)[train.index]
    y = np.column_stack([train[f"casos_Dengue_h{h}"] for h in H])
    regressor = sp.fit_count(train[columns], y, f["conteo"], seed, m_tr, **sp.e3_parameters(hyperparameters))
    fitted = sp.predict_count(regressor, train[columns], f["conteo"], m_tr)
    alphas = {h: sp.negative_binomial_dispersion(fitted[:, i], y[:, i]) for i, h in enumerate(H)}
    return Fit(regressor, alphas, train)


def predict_counts(regressor, frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
    """μ of t+2, t+3 and t+4 (one column per output) for the rows of ``frame``."""
    frame = frame.reset_index(drop=True)
    return sp.predict_count(regressor, frame[columns], sp.FORMULATIONS[FORMULATION]["conteo"], margin(frame))


def fit_persistence_weight(mu, persistence, y, grid: np.ndarray = W_GRID) -> float:
    """``w`` of the grid with the lowest MAE of ``w · μ + (1 − w) · persistence``; ties -> the largest ``w``."""
    mu, persistence, y = (np.asarray(v, float) for v in (mu, persistence, y))
    if not len(y):
        return 1.0
    mae = np.array([np.abs(w * mu + (1 - w) * persistence - y).mean() for w in grid])
    best = np.flatnonzero(np.isclose(mae, mae.min(), rtol=0, atol=1e-12))
    return float(grid[best.max()])


def published_count(mu, persistence, w: float) -> np.ndarray:
    return w * np.asarray(mu, float) + (1 - w) * np.asarray(persistence, float)
