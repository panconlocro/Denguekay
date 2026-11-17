"""E12: reporting delays simulated at every forecast origin (``protocolo_revision.md``).

The surveillance file has no notification dates, so the delays are assumed. One multinomial draw per district-week
splits the final count into cases reported 0, 1, 2 and 3 weeks after the week closes. At origin ``o``, week ``o - j``
shows the cases with delay ``<= j``, so a later origin never sees fewer cases of the same week. Weeks ``o - 3`` and
earlier are complete. Outcomes, thresholds and weather keep the final data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import common as c

SCENARIOS = {"moderado": (0.60, 0.85, 0.95), "severo": (0.30, 0.60, 0.85)}  # completeness after 0, 1, 2 weeks
SEED = 20261114
OUT_DIR = c.ARMS_DIR / "retrasos"
CAP = 52  # weeks since the last case, capped as in ``denguekay.evaluation.onsets``
SLOPE = np.array([-0.3, -0.1, 0.1, 0.3])  # OLS weights of a 4-week slope, oldest week first
RECENT = ["hist_lag_a", "hist_lag_b", "hist_media_4", "hist_semanas_pos_4", "propia_semanas_desde_ultimo_caso",
          "propia_pendiente_4"]


def weekly(cases: pd.DataFrame) -> pd.DataFrame:
    """Weeks (rows, without gaps) by district (columns) of the final confirmed counts."""
    table = cases.pivot(index="semana_inicio", columns="ubigeo", values="casos_Dengue").sort_index()
    if table.isna().any().any() or not table.index.to_series().diff().dropna().dt.days.eq(7).all():
        raise ValueError("The case series has missing district-weeks")
    return table.astype(np.int64)


def reported(final: pd.DataFrame, completeness, seed: int = SEED) -> np.ndarray:
    """Cases of each week reported within 0, 1 and 2 weeks of its close (array: delay, week, district)."""
    c0, c1, c2 = completeness
    probs = np.array([c0, c1 - c0, c2 - c1, 1 - c2])
    if (probs < 0).any() or not np.isclose(probs.sum(), 1):
        raise ValueError(f"Invalid completeness {completeness}")
    split = np.random.default_rng(seed).multinomial(final.to_numpy(), probs)
    return np.cumsum(split, axis=-1)[..., :3].transpose(2, 0, 1)


def weeks_since_case(final: pd.DataFrame) -> np.ndarray:
    """``propia_semanas_desde_ultimo_caso`` of every week with final counts (``onsets.own_history``)."""
    y = final.to_numpy()
    last = pd.DataFrame(np.where(y > 0, np.arange(len(y))[:, None], np.nan)).ffill().to_numpy()
    return np.nan_to_num(np.arange(len(y))[:, None] - last, nan=CAP).clip(max=CAP)


def vintage_history(origins: pd.DataFrame, cases: pd.DataFrame, completeness, seed: int = SEED) -> pd.DataFrame:
    """Case-history predictors of every origin computed from the counts reported by that origin's close."""
    final = weekly(cases)
    rep = reported(final, completeness, seed)
    row = final.index.get_indexer(origins.origen_cierre - 6 * c.DAY)
    col = final.columns.get_indexer(origins.ubigeo)
    if (row < 3).any() or (col < 0).any():
        raise ValueError("Origins outside the case series")
    v0, v1, v2 = rep[0, row, col], rep[1, row - 1, col], rep[2, row - 2, col]
    y3 = final.to_numpy()[row - 3, col]
    recent = np.column_stack([y3, v2, v1, v0])
    since = np.where(v0 > 0, 0, np.where(v1 > 0, 1, np.where(v2 > 0, 2,
                     np.minimum(3 + weeks_since_case(final)[row - 3, col], CAP))))
    return pd.DataFrame({"hist_lag_a": v0, "hist_lag_b": v1, "hist_media_4": recent.mean(axis=1),
                         "hist_semanas_pos_4": (recent > 0).sum(axis=1), "propia_semanas_desde_ultimo_caso": since,
                         "propia_pendiente_4": np.log1p(recent) @ SLOPE}, index=origins.index)


def origin_counts(frame: pd.DataFrame, cases: pd.DataFrame, completeness, seed: int = SEED) -> np.ndarray:
    """Count of the origin week as reported at its close, for rows with ``ubigeo`` and ``origen_cierre``."""
    final = weekly(cases)
    rep = reported(final, completeness, seed)
    row = final.index.get_indexer(frame.origen_cierre - 6 * c.DAY)
    col = final.columns.get_indexer(frame.ubigeo)
    if (row < 0).any() or (col < 0).any():
        raise ValueError("Rows outside the case series")
    return rep[0, row, col]


def delayed(inputs: dict, origins: pd.DataFrame, completeness, seed: int = SEED) -> tuple[dict, pd.DataFrame]:
    """Inputs and origins of one scenario: recent case history, offset and persistence as reported at the origin."""
    history = vintage_history(origins, inputs["casos"], completeness, seed)
    out = origins.copy()
    out[RECENT] = history[RECENT].astype(out[RECENT].dtypes.to_dict())
    out["persistencia"] = history.hist_lag_a.to_numpy()
    matrices = {h: m.assign(persistencia=origin_counts(m, inputs["casos"], completeness, seed).astype(m.persistencia.dtype))
                for h, m in inputs["matrices"].items()}
    return {**inputs, "matrices": matrices}, out
