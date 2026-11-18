"""E11: onset versus continuation (``protocolo_revision.md``; event measures as in ``protocolo_revision_enmienda_1.md``).

The origin state (quiet: no elevated week in the four weeks up to the origin; active otherwise) is known when the
forecast is issued, so Brier scores within each state remain proper. Onset weeks are defined from the outcome and are
used only for event measures. Detection and false alarms are always counted under the same alert policy, and
forecasts are compared at matched false-alarm budgets.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

import common as c
import experiments as ex

ALERT_THRESHOLDS = (0.1, 0.2)
WINDOW = 4  # quiet: weeks o-3..o not elevated; onset: weeks t-4..t-1 not elevated
POLICIES = {"4 weeks ahead": (4,), "any of 2-4 weeks ahead": (2, 3, 4)}
BUDGETS = (1.0, 2.0, 3.0)  # false alarms per district per 52 weeks
CURVE_CAP = 10.0  # full threshold resolution up to this false-alarm rate, coarse beyond it


def elevated(labels: pd.DataFrame) -> pd.DataFrame:
    """Weeks (rows, without gaps) by district (columns) of the elevated-week outcome."""
    table = labels.pivot(index="semana_inicio", columns="ubigeo", values="brote").sort_index()
    if table.isna().any().any() or not table.index.to_series().diff().dropna().dt.days.eq(7).all():
        raise ValueError("The label series has missing district-weeks")
    return table.astype(int)


def origin_state(frame: pd.DataFrame, labels: pd.DataFrame) -> np.ndarray:
    """``quiet`` or ``active`` for rows with ``ubigeo`` and ``origen_cierre``."""
    table = elevated(labels)
    recent = table.rolling(WINDOW, min_periods=WINDOW).max().to_numpy()
    row = table.index.get_indexer(frame.origen_cierre - 6 * c.DAY)
    col = table.columns.get_indexer(frame.ubigeo)
    if (row < 0).any() or (col < 0).any() or np.isnan(recent[row, col]).any():
        raise ValueError("Origin state unknown for some rows")
    return np.where(recent[row, col] > 0, "active", "quiet")


def onset_weeks(labels: pd.DataFrame) -> pd.DataFrame:
    """Elevated weeks ``t`` with none of the weeks ``t-4..t-1`` elevated."""
    table = elevated(labels)
    before = table.shift(1).rolling(WINDOW, min_periods=WINDOW).max()
    onset = table.eq(1) & before.eq(0)
    out = onset.stack().rename("inicio").reset_index()
    return out[out.inicio][["ubigeo", "semana_inicio"]].reset_index(drop=True)


def onset_alerts(frame: pd.DataFrame, prob: str, onsets: pd.DataFrame, thresholds=ALERT_THRESHOLDS) -> pd.DataFrame:
    """Per seed, threshold and onset week: alert at each horizon, detection and warning time (longest horizon)."""
    f = ex.seasons_only(frame).merge(onsets, on=["ubigeo", "semana_inicio"], how="inner", validate="many_to_one")
    if "semilla" not in f:
        f["semilla"] = 0
    rows = []
    for t in thresholds:
        wide = (f.assign(alerta=f[prob].ge(t))
                .pivot_table(index=["semilla", "temporada", "ubigeo", "semana_inicio"], columns="horizonte",
                             values="alerta", aggfunc="first"))
        if wide.isna().any().any():
            raise ValueError("An onset week lacks a forecast at some horizon")
        wide = wide.astype(bool)
        warning = np.select([wide[4], wide[3], wide[2]], [4, 3, 2], default=0)
        rows.append(wide.reset_index().assign(umbral=t, detectado=warning > 0, aviso_4=wide[4].to_numpy(),
                                              semanas_aviso=warning))
    return pd.concat(rows, ignore_index=True).rename(columns={2: "alerta_h2", 3: "alerta_h3", 4: "alerta_h4"})


def policy_scores(frame: pd.DataFrame, prob: str, onsets: pd.DataFrame, horizons) -> pd.DataFrame:
    """Per seed and target week: the highest probability among the forecasts issued at ``horizons`` (an alert is
    raised when it reaches the threshold), the outcome, and whether the week is an onset week."""
    f = ex.seasons_only(frame)
    if "semilla" not in f:
        f["semilla"] = 0
    f = f[f.horizonte.isin(horizons)]
    g = (f.groupby(["semilla", "temporada", "ubigeo", "semana_inicio"])
         .agg(brote=("brote", "first"), puntaje=(prob, "max"), horizontes=("horizonte", "nunique")).reset_index())
    if not g.horizontes.eq(len(horizons)).all():
        raise ValueError("A target week lacks a forecast at some horizon")
    g = g.merge(onsets.assign(inicio=True), on=["ubigeo", "semana_inicio"], how="left", validate="many_to_one")
    return g.assign(inicio=g.inicio.eq(True)).drop(columns="horizontes")


def fixed_thresholds(scores: pd.DataFrame, thresholds=ALERT_THRESHOLDS) -> pd.DataFrame:
    """Per seed and threshold: share of onset weeks with an alert and false alarms per district per 52 weeks, both
    counted under the alert policy of ``scores``."""
    rows = []
    for seed, g in scores.groupby("semilla"):
        for t in thresholds:
            alert = g.puntaje.ge(t)
            rows.append({"semilla": seed, "umbral": t, "detectados_%": 100 * alert[g.inicio].mean(),
                         "falsas_alarmas": 52 * (alert & g.brote.eq(0)).sum() / len(g)})
    return pd.DataFrame(rows)


def _curves(scores: pd.DataFrame, cap: float) -> tuple[list, dict]:
    """Per seed: false alarms and detected onsets of each season at every distinct threshold, from the highest down
    until the pooled false-alarm rate reaches ``cap`` per district per 52 weeks, then at 201 quantiles down to
    alerting on every week, so that reweighted bootstrap samples reach every budget (column 0: no alert)."""
    seasons = sorted(scores.temporada.unique())
    out = {}
    for seed, g in scores.groupby("semilla"):
        ordered = np.sort(g.puntaje[g.brote.eq(0)].to_numpy())[::-1]
        stop = ordered[min(int(np.ceil(cap * len(g) / 52)), len(ordered) - 1)]
        every = g.puntaje.to_numpy()
        head = np.unique(every[every >= stop])[::-1]  # all distinct scores, so onsets between false alarms count early
        rest = every[every < stop]
        tail = np.unique(np.quantile(rest, np.linspace(0, 1, 201)))[::-1] if len(rest) else rest
        grid = np.concatenate([head, tail])  # coarse tail down to alerting on every week
        fa = np.zeros((len(seasons), len(grid) + 1))
        det = np.zeros_like(fa)
        rows, onsets = np.zeros(len(seasons)), np.zeros(len(seasons))
        for i, season in enumerate(seasons):
            d = g[g.temporada.eq(season)]
            negative = np.sort(d.puntaje[d.brote.eq(0)].to_numpy())
            positive = np.sort(d.puntaje[d.inicio].to_numpy())
            fa[i, 1:] = len(negative) - np.searchsorted(negative, grid, side="left")
            det[i, 1:] = len(positive) - np.searchsorted(positive, grid, side="left")
            rows[i], onsets[i] = len(d), len(positive)
        out[seed] = (fa, det, rows, onsets)
    return seasons, out


def _at_budgets(fa, det, rows, onsets, weights: np.ndarray, budgets) -> np.ndarray:
    """Share of onsets detected at each false-alarm budget, for every row of season weights (draws x budgets).
    Linear interpolation between adjacent thresholds equals alerting on a random share of tied forecasts."""
    rate = 52 * (weights @ fa) / (weights @ rows)[:, None]
    share = (weights @ det) / (weights @ onsets)[:, None]
    idx = np.arange(len(weights))
    out = []
    for b in budgets:
        j = (rate < b).sum(axis=1)
        if (j >= rate.shape[1]).any():
            raise ValueError(f"Budget {b} beyond the computed curve")
        r0, r1, s0, s1 = rate[idx, j - 1], rate[idx, j], share[idx, j - 1], share[idx, j]
        out.append(s0 + np.where(r1 > r0, (b - r0) / np.where(r1 > r0, r1 - r0, 1), 1.0) * (s1 - s0))
    return np.column_stack(out)


def _season_detection(fa, det, rows, onsets, budgets) -> np.ndarray:
    """Share of onsets detected in each season at the pooled matched threshold (seasons x budgets; NaN without onsets)."""
    rate = 52 * fa.sum(0) / rows.sum()
    out = []
    for b in budgets:
        j = int((rate < b).sum())
        frac = (b - rate[j - 1]) / (rate[j] - rate[j - 1]) if rate[j] > rate[j - 1] else 1.0
        hits = det[:, j - 1] + frac * (det[:, j] - det[:, j - 1])
        out.append(np.where(onsets > 0, hits / np.where(onsets > 0, onsets, 1), np.nan))
    return np.column_stack(out)


def matched_budgets(scores_by_forecast: dict, pairs, budgets=BUDGETS, draws: int = ex.DRAWS, chunk: int = 1000):
    """Detection at matched false-alarm budgets (median over seeds) and paired differences, with the whole-season
    bootstrap re-matching the budget in every sample (seeds paired; a single-seed forecast is used for every seed)."""
    curves, seasons = {}, None
    for name, scores in scores_by_forecast.items():
        found, curves[name] = _curves(scores, CURVE_CAP)
        if seasons is not None and found != seasons:
            raise ValueError("Forecasts cover different seasons")
        seasons = found
    counts = np.random.default_rng(ex.BOOT_SEED).multinomial(len(seasons), np.full(len(seasons), 1 / len(seasons)),
                                                             size=draws).astype(float)
    point, boot, per_season = {}, {}, {}
    for name, per_seed in curves.items():
        point[name] = np.median([_at_budgets(*c_, np.ones((1, len(seasons))), budgets)[0] for c_ in per_seed.values()], axis=0)
        boot[name] = np.median([np.vstack([_at_budgets(*c_, counts[i:i + chunk], budgets) for i in range(0, draws, chunk)])
                                for c_ in per_seed.values()], axis=0)
        per_season[name] = np.median([_season_detection(*c_, budgets) for c_ in per_seed.values()], axis=0)
    levels = pd.DataFrame([{"modelo": name, "presupuesto": b, "detectados_%": 100 * point[name][k]}
                           for name in curves for k, b in enumerate(budgets)])
    rows = []
    for a, b_ in pairs:
        diff = 100 * (boot[a] - boot[b_])
        better = per_season[a] > per_season[b_]
        with_onsets = ~np.isnan(per_season[a])
        for k, b in enumerate(budgets):
            rows.append({"comparacion": f"{a} vs {b_}", "presupuesto": b,
                         "diferencia_pp": 100 * (point[a][k] - point[b_][k]),
                         "ic95": tuple(round(float(x), 2) for x in np.percentile(diff[:, k], [2.5, 97.5])),
                         "temporadas_a_mejor": int(better[with_onsets[:, k], k].sum()),
                         "temporadas_con_inicios": int(with_onsets[:, k].sum())})
    return levels, pd.DataFrame(rows)


def pooled_ap(frame: pd.DataFrame, prob: str) -> pd.DataFrame:
    """Average precision pooled over the evaluated seasons, per horizon (median over seeds)."""
    f = ex.seasons_only(frame)
    if "semilla" not in f:
        f["semilla"] = 0
    ap = f.groupby(["semilla", "horizonte"]).apply(
        lambda g: average_precision_score(g.brote, g[prob]) if g.brote.any() else np.nan, include_groups=False)
    return ap.groupby("horizonte").median().rename("ap").reset_index()
