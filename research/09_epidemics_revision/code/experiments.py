"""Scoring of the study-09 experiments: paired Brier contrasts, season bootstrap, CORP, counts, net benefit.

Conventions (protocol): the 18 complete seasons 2009–2026; ``pooled`` = ratio of summed squared errors over all
district-weeks, per seed, then the median over seeds; ``equal-season`` = relative change per season (median over
seeds), averaged over seasons; intervals from 20,000 whole-season bootstrap draws (seed 20261113), seeds paired.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score

import common as c

PRED_COLUMNS = ["semilla", "bloque", "horizonte", "ubigeo", "semana_inicio", "origen_cierre", "casos_Dengue",
                "brote", "umbral_brote_casos", "persistencia", "mu_modelo", "w_mezcla", "conteo_publicado",
                "alpha_usada", "probabilidad_cruda", "probabilidad_calibrada"]
KEY = ["bloque", "horizonte", "ubigeo", "semana_inicio"]
DRAWS, BOOT_SEED = 20_000, 20261113


def seasons_only(frame: pd.DataFrame, seasons=c.SEASONS) -> pd.DataFrame:
    out = frame.assign(temporada=c.season_of(frame.bloque))
    return out[out.temporada.isin(seasons)].copy()


def sse(frame: pd.DataFrame, prob: str = "probabilidad_calibrada", seasons=c.SEASONS) -> pd.DataFrame:
    """Summed squared error, rows and events per seed, season and horizon."""
    f = seasons_only(frame, seasons)
    if f[prob].isna().any():
        raise ValueError(f"Missing {prob} in the evaluated seasons")
    f["se"] = (f[prob] - f.brote) ** 2
    if "semilla" not in f:
        f["semilla"] = 0
    return (f.groupby(["semilla", "temporada", "horizonte"])
            .agg(sse=("se", "sum"), n=("se", "size"), eventos=("brote", "sum")).reset_index())


def sae(frame: pd.DataFrame, count: str = "conteo_publicado", seasons=c.SEASONS) -> pd.DataFrame:
    """Summed absolute error of a count forecast and rows per seed, season and horizon (E10)."""
    f = seasons_only(frame, seasons)
    f["ae"] = (f[count] - f.casos_Dengue).abs()
    if "semilla" not in f:
        f["semilla"] = 0
    return f.groupby(["semilla", "temporada", "horizonte"]).agg(sae=("ae", "sum"), n=("ae", "size")).reset_index()


def _matrices(a: pd.DataFrame, b: pd.DataFrame, h: int, value: str = "sse"):
    a, b = a[a.horizonte.eq(h)], b[b.horizonte.eq(h)]
    seeds = sorted(a.semilla.unique())
    if set(b.semilla) == {0}:
        b = pd.concat([b.assign(semilla=s) for s in seeds], ignore_index=True)
    seasons = sorted(a.temporada.unique())
    A = a.pivot(index="semilla", columns="temporada", values=value).loc[seeds, seasons].to_numpy()
    B = b.pivot(index="semilla", columns="temporada", values=value).loc[seeds, seasons].to_numpy()
    na = a.pivot(index="semilla", columns="temporada", values="n").loc[seeds, seasons].to_numpy()
    nb = b.pivot(index="semilla", columns="temporada", values="n").loc[seeds, seasons].to_numpy()
    if not np.array_equal(na, nb):
        raise ValueError("Arms are not paired on the same district-weeks")
    return A, B, na, seasons


def contrast(a: pd.DataFrame, b: pd.DataFrame, draws: int = DRAWS, value: str = "sse") -> pd.DataFrame:
    """Relative change in Brier (``value="sse"``) or in MAE (``"sae"``) of ``a`` vs ``b`` (negative favours ``a``),
    in percent; ``brier_a`` and ``brier_b`` then hold the pooled mean loss of each arm."""
    rng = np.random.default_rng(BOOT_SEED)
    rows = []
    for h in sorted(a.horizonte.unique()):
        A, B, n, seasons = _matrices(a, b, h, value)
        pooled = np.median(A.sum(1) / B.sum(1) - 1)
        per_season = np.median(A / B - 1, axis=0)
        counts = rng.multinomial(len(seasons), np.full(len(seasons), 1 / len(seasons)), size=draws)
        boot_pooled = np.median((counts @ A.T) / (counts @ B.T) - 1, axis=1)
        boot_equal = counts @ per_season / len(seasons)
        rows.append({
            "horizonte": h, "temporadas": len(seasons),
            "brier_a": np.median(A.sum(1) / n.sum(1)), "brier_b": np.median(B.sum(1) / n.sum(1)),
            "cambio_agrupado_%": 100 * pooled,
            "ic95_agrupado": tuple(round(float(x), 2) for x in 100 * np.percentile(boot_pooled, [2.5, 97.5])),
            "cambio_igual_peso_%": 100 * per_season.mean(),
            "ic95_igual_peso": tuple(round(float(x), 2) for x in 100 * np.percentile(boot_equal, [2.5, 97.5])),
            "temporadas_a_mejor": int((per_season < 0).sum()),
        })
    return pd.DataFrame(rows)


def by_season(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Per-season relative change (median over seeds), with season prevalence."""
    rows = []
    for h in sorted(a.horizonte.unique()):
        A, B, n, seasons = _matrices(a, b, h)
        events = a[a.horizonte.eq(h) & a.semilla.eq(a.semilla.min())].set_index("temporada").eventos
        for j, s in enumerate(seasons):
            rows.append({"horizonte": h, "temporada": s, "prevalencia_%": 100 * events[s] / n[0, j],
                         "cambio_%": 100 * np.median(A[:, j] / B[:, j] - 1)})
    return pd.DataFrame(rows)


def leave_one_out(a: pd.DataFrame, b: pd.DataFrame, value: str = "sse") -> pd.DataFrame:
    rows = []
    for h in sorted(a.horizonte.unique()):
        A, B, _, seasons = _matrices(a, b, h, value)
        for j, s in enumerate(seasons):
            keep = np.arange(len(seasons)) != j
            rows.append({"horizonte": h, "omitida": s,
                         "cambio_agrupado_%": 100 * np.median(A[:, keep].sum(1) / B[:, keep].sum(1) - 1),
                         "cambio_igual_peso_%": 100 * np.median(A[:, keep] / B[:, keep] - 1, axis=0).mean()})
    return pd.DataFrame(rows)


def probability_diagnostics(frame: pd.DataFrame, prob: str = "probabilidad_calibrada", label: str = "") -> pd.DataFrame:
    """CORP, AP, calibration slope and intercept per seed, season and horizon."""
    f = seasons_only(frame)
    if "semilla" not in f:
        f["semilla"] = 0
    rows = []
    for (seed, season, h), g in f.groupby(["semilla", "temporada", "horizonte"]):
        y, p = g.brote.to_numpy(int), np.clip(g[prob].to_numpy(float), 1e-6, 1 - 1e-6)
        row = {"brazo": label, "semilla": seed, "temporada": season, "horizonte": h, **c.corp(p, y)}
        row["ap"] = average_precision_score(y, p) if y.any() else np.nan
        if 0 < y.sum() < len(y):
            fit = LogisticRegression(C=1e6, max_iter=1000).fit(np.log(p / (1 - p)).reshape(-1, 1), y)
            row["pendiente"], row["intercepto"] = float(fit.coef_[0][0]), float(fit.intercept_[0])
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_diagnostics(diag: pd.DataFrame) -> pd.DataFrame:
    """Paper convention: median over seeds within season, then mean over seasons."""
    fields = ["brier", "mcb", "dsc", "unc", "ap", "pendiente", "intercepto"]
    per_season = diag.groupby(["brazo", "horizonte", "temporada"])[fields].median()
    return per_season.groupby(["brazo", "horizonte"]).mean().reset_index()


def wis_nb2(y, mu, alpha, levels=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98)) -> np.ndarray:
    """Weighted interval score of NB2 predictive distributions (Bracher et al. 2021)."""
    y, mu = np.asarray(y, float), np.clip(np.asarray(mu, float), 1e-9, None)
    r = 1 / np.asarray(alpha, float)
    p = r / (r + mu)
    median = stats.nbinom.ppf(0.5, r, p)
    total = 0.5 * np.abs(y - median)
    for level in levels:
        a = 1 - level
        lo, hi = stats.nbinom.ppf(a / 2, r, p), stats.nbinom.ppf(1 - a / 2, r, p)
        total += (a / 2) * ((hi - lo) + (2 / a) * np.maximum(lo - y, 0) + (2 / a) * np.maximum(y - hi, 0))
    return total / (len(levels) + 0.5)


def count_scores(frame: pd.DataFrame, label: str, with_wis: bool = True) -> pd.DataFrame:
    """MAE, RMSE (published count) and WIS (NB2 centred on the published count) per seed, season and horizon."""
    f = seasons_only(frame)
    rows = []
    for (seed, season, h), g in f.groupby(["semilla", "temporada", "horizonte"]):
        err = g.conteo_publicado - g.casos_Dengue
        row = {"brazo": label, "semilla": seed, "temporada": season, "horizonte": h,
               "mae": err.abs().mean(), "rmse": np.sqrt((err ** 2).mean()),
               "mae_persistencia": (g.persistencia - g.casos_Dengue).abs().mean()}
        if with_wis:
            row["wis"] = wis_nb2(g.casos_Dengue, g.conteo_publicado, g.alpha_usada).mean()
        rows.append(row)
    return pd.DataFrame(rows)


def net_benefit(frame: pd.DataFrame, prob: str, thresholds=np.round(np.arange(0.05, 0.65, 0.05), 2),
                label: str = "") -> pd.DataFrame:
    """Net benefit of alerting when p >= t: (TP - FP * t/(1-t)) / n, per seed, season, horizon and threshold."""
    f = seasons_only(frame)
    if "semilla" not in f:
        f["semilla"] = 0
    rows = []
    for (seed, season, h), g in f.groupby(["semilla", "temporada", "horizonte"]):
        y, p = g.brote.to_numpy(int), g[prob].to_numpy(float)
        for t in thresholds:
            alert = p >= t
            tp, fp = int((alert & (y == 1)).sum()), int((alert & (y == 0)).sum())
            rows.append({"brazo": label, "semilla": seed, "temporada": season, "horizonte": h, "umbral": t,
                         "beneficio_neto": (tp - fp * t / (1 - t)) / len(y)})
    return pd.DataFrame(rows)


CALIBRATION_COLUMNS = ["semilla", "bloque", "horizonte", "ubigeo", "anio", "semana", "semana_inicio", "origen_cierre",
                       "casos_Dengue", "brote", "umbral_brote_casos", "persistencia", "mu_modelo", "alpha_usada",
                       "probabilidad_cruda", "probabilidad_calibrada"]


def recalibrate(frame: pd.DataFrame, raw: np.ndarray, method: str = "platt") -> np.ndarray:
    """Chronological calibration of ``raw`` (earlier blocks, labels closed by each block's cutoff)."""
    pred = frame.drop(columns=["probabilidad_cruda", "probabilidad_calibrada"], errors="ignore").assign(probabilidad_brote=raw)
    calibrated, _ = c.spatial.pa.calibrate_chronologically(pred, method=method)
    return calibrated.probabilidad_calibrada.to_numpy(float)


def out_of_sample_alpha(frame: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    """Raw NB2 exceedance with the dispersion fitted on earlier blocks' (mu, cases), labels closed by the cutoff.

    Falls back to the in-sample alpha when the fit does not converge or ends at an optimizer bound, or for the
    first block (no earlier rows).
    """
    sp, pa = c.spatial.sp, c.spatial.pa
    frame = frame.reset_index(drop=True)
    raw = np.full(len(frame), np.nan)
    record = []
    for h, by_h in frame.groupby("horizonte"):
        onsets = by_h.groupby("bloque").semana_inicio.min().sort_values()
        for block, start in onsets.items():
            idx = by_h.index[by_h.bloque.eq(block)]
            cutoff = pa.block_cutoff(by_h.loc[idx])
            prev = by_h[by_h.bloque.map(onsets).lt(start)]
            prev = prev[(prev.semana_inicio + 6 * c.DAY).le(cutoff)]
            alpha, source = float(frame.loc[idx[0], "alpha_usada"]), "in_sample"
            if len(prev):
                fit = sp.negative_binomial_dispersion_detail(prev.mu_modelo, prev.casos_Dengue)
                if fit["convergio"] and not fit["en_limite"]:
                    alpha, source = fit["alpha"], "out_of_sample"
            raw[idx] = sp.negative_binomial_probability(frame.loc[idx, "mu_modelo"], alpha, frame.loc[idx, "umbral_brote_casos"])
            record.append({"horizonte": h, "bloque": block, "alpha_in_sample": float(frame.loc[idx[0], "alpha_usada"]),
                           "alpha_used": alpha, "source": source, "rows": len(prev)})
    return raw, pd.DataFrame(record)


def nb2_exceedance(mu, alpha, k) -> np.ndarray:
    """P(cases >= k) under NB2(mu, alpha), for any integer k >= 1 (no 2-case floor)."""
    r = 1 / np.asarray(alpha, float)
    mu = np.clip(np.asarray(mu, float), 1e-9, None)
    return stats.nbinom.sf(np.asarray(k, float) - 1, r, r / (r + mu))


def relabel(frame: pd.DataFrame, k: np.ndarray) -> pd.DataFrame:
    """Same count forecasts, new event ``cases >= k``: NB2 exceedance from the stored mean and dispersion,
    then chronological Platt on the new labels (``evaluate_label_sensitivity`` procedure)."""
    out = frame.reset_index(drop=True).copy()
    k = np.asarray(k, float)
    out["brote"] = (out.casos_Dengue.to_numpy(float) >= k).astype(int)
    out["p_nueva"] = recalibrate(out, nb2_exceedance(out.mu_modelo, out.alpha_usada, k))
    return out


def relabel_persistence(support: pd.DataFrame, k: np.ndarray) -> pd.DataFrame:
    out = support.reset_index(drop=True).copy()
    k = np.asarray(k, float)
    out["brote"] = (out.casos_Dengue.to_numpy(float) >= k).astype(int)
    ratio = (out.persistencia + 0.5) / (k + 0.5)
    calendar = c.spatial.mmwr_epi_week(out.semana_inicio)
    pred = out.assign(anio=calendar.anio_epi, semana=calendar.semana_epi, probabilidad_brote=ratio / (1 + ratio))
    calibrated, _ = c.spatial.pa.calibrate_chronologically(pred.drop(columns=["persistencia_prob", "persistencia_det", "climatologia"], errors="ignore"))
    out["p_nueva"] = calibrated.probabilidad_calibrada.to_numpy(float)
    return out


def thresholds_without_epidemic_years(cases: pd.DataFrame, rows: pd.DataFrame, multiplier=1.5, look_back=5,
                                      min_years=3, quantile=0.75) -> tuple[np.ndarray, pd.DataFrame]:
    """Protocol D4: for target year Y, drop from the reference the years whose regional total is at or above the
    ``quantile`` of totals over 2000…Y−1 (past years only); use the ``look_back`` most recent remaining years."""
    data = cases.assign(semana_ref=cases.semana.clip(upper=52))
    yearly = data.groupby(["ubigeo", "anio", "semana_ref"]).casos_Dengue.sum()
    totals = data.groupby("anio").casos_Dengue.sum()
    districts = sorted(data.ubigeo.unique())
    index = pd.MultiIndex.from_product([districts, range(1, 53)], names=["ubigeo", "semana_ref"])
    matrix = yearly.unstack("anio").reindex(index=index).fillna(0)
    taus, record = [], []
    for year in sorted(rows.anio.unique()):
        past = totals[totals.index < year]
        epidemic = sorted(past[past >= past.quantile(quantile)].index) if len(past) else []
        kept = [y for y in sorted(past.index, reverse=True) if y not in epidemic][:look_back]
        used = sorted(kept) if len(kept) >= min_years else list(range(year - look_back, year))
        window = matrix.reindex(columns=used, fill_value=0)
        tau = (window.mean(axis=1) + multiplier * window.std(axis=1, ddof=1)).rename("umbral").reset_index()
        taus.append(tau.assign(anio=year))
        record.append({"anio_objetivo": year, "anios_epidemicos_excluidos": epidemic, "anios_referencia": used})
    table = pd.concat(taus, ignore_index=True)
    keyed = rows[["ubigeo", "anio", "semana"]].assign(semana_ref=rows.semana.clip(upper=52))
    merged = keyed.merge(table, on=["ubigeo", "anio", "semana_ref"], how="left", validate="many_to_one")
    if merged.umbral.isna().any():
        raise ValueError("Missing alternative threshold")
    return merged.umbral.to_numpy(float), pd.DataFrame(record)
