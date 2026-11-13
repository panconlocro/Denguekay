"""Climate matrix (``preregistration.CLIMATE_MATRIX``): anomalies of e1 and e2, the monotone Niño of n1, their
guards (G45 to G50) and the generic block, leave-one-season-out and SHAP helpers for every matrix variant.

e1: the 14 columns of d1 computed on weekly anomalies. The anomaly of a week is its value minus the climatology of
its district and epi week (53 shares the cell of 52), fitted with the weeks since 2000 whose Saturday is <= the
block's cutoff (as the B5 of study 05 and ``features.climate.fit_climatology``); it is recomputed inside the block
loop (``prepare_block``). The windows are those of d1 (mean for rainfall, temperature and humidity; sum for the
days >= 20 mm), so e1 uses exactly the weeks d1 uses.

n1: the columns of b3 with ``monotone_constraints`` +1 on nino12_anom_media3 and 0 on the rest.
"""

import numpy as np
import pandas as pd

from denguekay.data.calendar import mmwr_epi_week
from denguekay.model import probabilistic_output as sp

import phase3_onsets as p3
import phase_d_weather_windows as pdw
import preregistration as pr

CLIMATE_START = pd.Timestamp("2000-01-01")
NINO = "nino12_anom_media3"
# weekly series of e1: value column -> (window spec, aggregation, prefix of the e1 columns)
E1_SERIES = {
    "precip_total_mm": (pdw.WINDOWS, "mean", "precip_total_mm_anomalia"),
    "temp_media": (pdw.WINDOWS, "mean", "temp_media_anomalia"),
    "hum_rel_media": (pdw.WINDOWS, "mean", "hum_rel_media_anomalia"),
    "dias_fuertes": (pdw.HEAVY_WINDOWS, "sum", "dias_precip_20mm_anomalia"),
}
D1_PREFIX = {"precip_total_mm": "precip_total_mm", "temp_media": "temp_media", "hum_rel_media": "hum_rel_media",
             "dias_fuertes": pdw.HEAVY_PREFIX}


def epi_week_cell(weeks: pd.Series) -> np.ndarray:
    """Climatological cell of each week: its MMWR epi week, 53 sharing the cell of 52."""
    return np.minimum(mmwr_epi_week(pd.Series(pd.to_datetime(weeks))).semana_epi.to_numpy(int), 52)


def weekly_series(sources: dict) -> dict[str, pd.DataFrame]:
    """The four weekly series of e1 (``ubigeo``, ``semana_inicio``, value, and ``fecha_disponible`` for CHIRPS)."""
    chirps = sources["chirps"][["ubigeo", "semana_inicio", "precip_total_mm", "fecha_disponible"]].copy()
    era5 = sources["era5"]
    heavy = sources["semanal_diario"][["ubigeo", "semana_inicio", "dias_fuertes"]].merge(
        chirps[["ubigeo", "semana_inicio", "fecha_disponible"]], on=["ubigeo", "semana_inicio"], how="inner",
        validate="one_to_one")
    out = {"precip_total_mm": chirps, "dias_fuertes": heavy,
           "temp_media": era5[["ubigeo", "semana_inicio", "temp_media"]].copy(),
           "hum_rel_media": era5[["ubigeo", "semana_inicio", "hum_rel_media"]].copy()}
    for d in out.values():
        d["ubigeo"] = d.ubigeo.astype(str)
        d["semana_inicio"] = pd.to_datetime(d.semana_inicio)
        d["celda"] = epi_week_cell(d.semana_inicio)
    return out


def climatology(weekly: pd.DataFrame, value: str, cutoff=None, exclude=None) -> pd.DataFrame:
    """Mean of ``value`` per district and climatological cell with the weeks since 2000 whose Saturday is <=
    ``cutoff`` (if given) and outside ``exclude`` = (first, last week start) (if given). Every district must have
    the 52 cells."""
    w = weekly[weekly.semana_inicio.ge(CLIMATE_START) & weekly[value].notna()]
    if cutoff is not None:
        w = w[(w.semana_inicio + pd.Timedelta(days=6)).le(pd.Timestamp(cutoff))]
    if exclude is not None:
        w = w[~w.semana_inicio.between(*exclude)]
    table = w.groupby(["ubigeo", "celda"], as_index=False)[value].mean().rename(columns={value: "climatologia"})
    expected = len(weekly.ubigeo.unique()) * 52
    if len(table) != expected:
        raise ValueError(f"Climatología de {value} incompleta: {len(table)} de {expected} celdas")
    return table


def anomalies(weekly: pd.DataFrame, value: str, clim: pd.DataFrame) -> pd.DataFrame:
    out = weekly.merge(clim, on=["ubigeo", "celda"], how="left", validate="many_to_one")
    out[value] = out[value] - out["climatologia"]
    return out.drop(columns="climatologia")


def e1_by_week(series: dict[str, pd.DataFrame], cutoff=None, exclude=None, clim_only: bool = False) -> pd.DataFrame:
    """Per district and origin week: the 14 e1 columns (or, with ``clim_only``, the same windows of the
    climatology itself, for G45) and the first and last week each source uses."""
    out = None
    for value, (windows, how, prefix) in E1_SERIES.items():
        w = series[value]
        clim = climatology(w, value, cutoff, exclude)
        if clim_only:
            a = w.merge(clim, on=["ubigeo", "celda"], how="left", validate="many_to_one")
            a[value] = a["climatologia"]
            a = a.drop(columns="climatologia")
        else:
            a = anomalies(w, value, clim)
        cols = ["ubigeo", "semana_inicio", value] + (["fecha_disponible"] if "fecha_disponible" in a else [])
        t = pdw.windows_by_origin_week(a[cols], value, windows, how=how, prefix=prefix)
        out = t if out is None else out.merge(t, on=["ubigeo", "semana_origen"], how="outer", validate="one_to_one")
    return out


class E1Builder:
    """Adds the e1 columns to the origins for a cutoff (block) or an excluded period (leave one season out)."""

    def __init__(self, sources: dict):
        self.series = weekly_series(sources)
        self.cache = {}

    def table(self, cutoff=None, exclude=None) -> pd.DataFrame:
        key = (None if cutoff is None else pd.Timestamp(cutoff), exclude)
        if key not in self.cache:
            self.cache[key] = e1_by_week(self.series, cutoff, exclude)
        return self.cache[key]

    def add(self, origins: pd.DataFrame, cutoff=None, exclude=None) -> pd.DataFrame:
        table = self.table(cutoff, exclude)
        base = origins.drop(columns=[c for c in table.columns if c in origins and c not in ("ubigeo",)], errors="ignore")
        return pdw.add_windows(base, table)

    def prepare_block(self):
        return lambda origins, cutoff: self.add(origins, cutoff=cutoff)


# --- n1 ----------------------------------------------------------------------------------------------------------

def monotone_hp(hp: dict, columns: list[str], spec: dict[str, int]) -> dict:
    """``hp`` plus ``monotone_constraints`` aligned with ``columns`` (``spec``: column -> +1/-1; the rest 0)."""
    return {**hp, "monotone_constraints": tuple(int(spec.get(c, 0)) for c in columns)}


# --- Generic block fit (any block, optional prepare) and guards -------------------------------------------------

def fit_block(inp: dict, origins: pd.DataFrame, block: tuple[str, str, int], seed: int, columns: list[str],
              hp: dict, prepare=None) -> dict:
    """Refit one block's regressor exactly as ``phase3_onsets.predict_blocks_weighted``."""
    from denguekay.model import horizon_strategies as eh

    _, kind, period = block
    _, cutoff = eh._common_cutoffs(inp["matrices"], kind, period)
    o = prepare(origins, cutoff) if prepare is not None else origins
    margin_all = sp.e3_margin(origins, p3.FORMULATION)
    train = p3._training(o, cutoff)
    reg, alphas = p3._fit(train, seed, list(columns), sp.e3_parameters(hp), margin_all, None)
    return {"regresor": reg, "alphas": alphas, "origenes": o, "margen": margin_all, "corte": cutoff,
            "x_reg": train[list(columns)]}


def monotone_check(fit: dict, columns: list[str], n: int = 1000, grid=np.linspace(-3, 6, 19), seed: int = 0) -> dict:
    """G49: for ``n`` random origins since 2005 and the Niño over ``grid``, μ never goes down in any horizon."""
    f = sp.FORMULATIONS[p3.FORMULATION]
    o = fit["origenes"]
    pool = np.flatnonzero(pd.to_datetime(o.origen_cierre).ge("2005-01-01").to_numpy())
    idx = np.random.default_rng(seed).choice(pool, size=min(n, len(pool)), replace=False)
    x = o.iloc[idx][list(columns)].reset_index(drop=True)
    preds = []
    for v in grid:
        xv = x.copy()
        xv[NINO] = v
        preds.append(sp.predict_count(fit["regresor"], xv, f["conteo"], fit["margen"][idx]))
    p = np.stack(preds)                      # grid x origins x horizons
    worst = float(np.diff(p, axis=0).min())
    return {"origenes": len(idx), "puntos_de_la_grilla": len(grid), "peor_diferencia": worst, "pasa": worst >= -1e-9}


def platt_slopes(pred: pd.DataFrame) -> pd.DataFrame:
    """Slope of the Platt fitted for each block and horizon, as ``protocol.calibrate_chronologically`` does."""
    from denguekay.evaluation import protocol as pa

    data = pred.copy()
    data["semana_inicio"] = pd.to_datetime(data.semana_inicio)
    data["origen_cierre"] = pd.to_datetime(data.origen_cierre)
    rows = []
    for h, by_h in data.groupby("horizonte"):
        onsets = by_h.groupby("bloque").semana_inicio.min().sort_values()
        for block, start in onsets.items():
            cutoff = pa.block_cutoff(by_h[by_h.bloque.eq(block)])
            prev = by_h[by_h.bloque.map(onsets).lt(start)]
            avail = prev[(prev.semana_inicio + pd.Timedelta(days=6)).le(cutoff)]
            if avail.brote.nunique() < 2:
                continue
            m = pa.fit_platt(avail.probabilidad_brote.to_numpy(float), avail.brote.to_numpy(int))
            rows.append({"horizonte": h, "bloque": block, "pendiente": float(m.coef_[0][0]),
                         "intercepto": float(m.intercept_[0])})
    return pd.DataFrame(rows)


def guard_e1_definition(builder: E1Builder, origins_with_d1: pd.DataFrame, cutoff, tol: float = 1e-9) -> dict:
    """G45 (real data): for the block's cutoff, e1 + the same window of the climatology = d1, on every origin with
    a value."""
    e1 = pdw.add_windows(origins_with_d1[["ubigeo", "origen_cierre"]], builder.table(cutoff))
    clim = pdw.add_windows(origins_with_d1[["ubigeo", "origen_cierre"]], e1_by_week(builder.series, cutoff, clim_only=True))
    worst, missing = 0.0, 0
    for value, (windows, _, prefix) in E1_SERIES.items():
        for w in windows:
            d1 = origins_with_d1[f"{D1_PREFIX[value]}_{w}"].to_numpy(float)
            total = e1[f"{prefix}_{w}"].to_numpy(float) + clim[f"{prefix}_{w}"].to_numpy(float)
            ok = ~np.isnan(d1)
            missing += int(np.isnan(total[ok]).sum())
            if ok.any():
                worst = max(worst, float(np.nanmax(np.abs(total[ok] - d1[ok]))))
    return {"corte": str(pd.Timestamp(cutoff).date()), "diferencia_maxima": worst, "vacios_donde_d1_tiene_valor": missing,
            "pasa": bool(worst <= tol and missing == 0)}


def guard_e1_cutoff(sources: dict, origins: pd.DataFrame, cutoff) -> dict:
    """G47 (real data): changing every weather value after the block's cutoff changes neither its climatology nor the
    e1 columns of the origins whose week closes by the cutoff."""
    cutoff = pd.Timestamp(cutoff)
    base = E1Builder(sources)
    altered_sources = {}
    for k, d in sources.items():
        d = d.copy()
        later = pd.to_datetime(d.semana_inicio) > cutoff
        for c in ("precip_total_mm", "temp_media", "hum_rel_media", "dias_fuertes"):
            if c in d:
                d.loc[later, c] = d.loc[later, c] * 3 + 11
        altered_sources[k] = d
    other = E1Builder(altered_sources)
    same_clim = all(climatology(base.series[v], v, cutoff).equals(climatology(other.series[v], v, cutoff)) for v in E1_SERIES)
    early = pd.to_datetime(origins.origen_cierre).le(cutoff)
    a = base.add(origins[early], cutoff=cutoff)[pr.MATRIX_E1].to_numpy(float)
    b = other.add(origins[early], cutoff=cutoff)[pr.MATRIX_E1].to_numpy(float)
    same_cols = bool(np.array_equal(a, b, equal_nan=True))
    return {"corte": str(cutoff.date()), "origenes_hasta_el_corte": int(early.sum()), "climatologia_igual": same_clim,
            "columnas_iguales": same_cols, "pasa": bool(same_clim and same_cols)}


def guard_e1_coverage(builder: E1Builder, origins: pd.DataFrame, cutoffs, last_close) -> dict:
    """G48: with every block's climatology, no origin from 2005 to the last one used lacks an e1 column, and e1 uses
    the same first and last weeks as d1 (so the availability of G43 applies)."""
    close = pd.to_datetime(origins.origen_cierre)
    sel = close.ge("2005-01-01") & close.le(pd.Timestamp(last_close))
    missing, weeks_differ = 0, 0
    for c in cutoffs:
        o = builder.add(origins[sel], cutoff=c)
        missing += int(o[pr.MATRIX_E1].isna().any(axis=1).sum())
        for value, (_, _, prefix) in E1_SERIES.items():
            for edge in ("primera_semana", "ultima_semana"):
                weeks_differ += int((pd.to_datetime(o[f"{prefix}_{edge}"]) != pd.to_datetime(o[f"{D1_PREFIX[value]}_{edge}"])).sum())
    return {"bloques": len(cutoffs), "origenes": int(sel.sum()), "sin_valor": missing, "semanas_distintas_de_d1": weeks_differ,
            "pasa": missing == 0 and weeks_differ == 0}


# --- Leave one season out for any variant -------------------------------------------------------------------------

def loso_predictions(inp: dict, origins: pd.DataFrame, columns: list[str], hp: dict, seed: int,
                     seasons=None, buffer_weeks: int = pr.CLIMATOLOGY_BUFFER_WEEKS, builder: E1Builder | None = None
                     ) -> pd.DataFrame:
    """``phase_2026.loso_predictions`` with, for e1/e2, the climatology fitted outside the left-out season widened
    by ``buffer_weeks`` (the same weeks excluded from the training)."""
    import phase_2026 as p26
    from denguekay.model import horizon_strategies as eh

    seasons = seasons or p26.LOSO_SEASONS
    f = sp.FORMULATIONS[p3.FORMULATION]
    extra = sp.e3_parameters(hp)
    margin_all = sp.e3_margin(origins, p3.FORMULATION)
    parts = []
    for s in seasons:
        tests = {h: eh.split(inp["matrices"][h], "temporada", s)[1] for h in p3.H}
        start = min(t.semana_inicio.min() for t in tests.values()) - pd.Timedelta(weeks=buffer_weeks)
        end = max(t.semana_inicio.max() for t in tests.values()) + pd.Timedelta(weeks=buffer_weeks, days=6)
        o = builder.add(origins, exclude=(start, end)) if builder is not None else origins
        complete = o.dropna(subset=[f"semana_inicio_h{h}" for h in p3.H])
        complete = complete[pd.to_datetime(complete.origen_cierre).ge("2005-01-01")]
        inside = lambda col: pd.to_datetime(col).between(start, end)
        touch = inside(pd.to_datetime(complete.origen_cierre) - pd.Timedelta(days=6))
        for h in p3.H:
            touch |= inside(complete[f"semana_inicio_h{h}"])
        train = complete[~touch]
        reg, alphas = p3._fit(train, seed, list(columns), extra, margin_all, None)
        counts = sp.predict_count(reg, o[list(columns)], f["conteo"], margin_all)
        for step, h in enumerate(p3.H):
            pr_ = pd.DataFrame({"ubigeo": o.ubigeo, "semana_inicio": o[f"semana_inicio_h{h}"],
                                "casos_predichos": counts[:, step]})
            test = tests[h].merge(pr_.dropna(subset=["semana_inicio"]), on=["ubigeo", "semana_inicio"], how="left",
                                  validate="one_to_one")
            if test.casos_predichos.isna().any():
                raise ValueError(f"Predicciones incompletas al dejar fuera {s} h={h}")
            test["probabilidad_brote"] = sp.negative_binomial_probability(test.casos_predichos, alphas[step],
                                                                          test.umbral_brote_casos)
            parts.append(eh._output(test, f"fuera_{s}", test.casos_predichos, test.probabilidad_brote))
    return pd.concat(parts, ignore_index=True)


def loso_better_cells(loso: pd.DataFrame, variant: str, reference: str = "L + 5a") -> int:
    """Cells (season x horizon) where the variant's leave-one-season-out Brier is strictly below the reference's."""
    a = loso[loso.variante.eq(variant)].set_index(["horizonte", "bloque"]).brier
    b = loso[loso.variante.eq(reference)].set_index(["horizonte", "bloque"]).brier
    return int((a < b.reindex(a.index)).sum())
