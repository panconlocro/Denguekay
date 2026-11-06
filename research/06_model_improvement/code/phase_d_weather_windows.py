"""Climate step d: weather windows over L + 5a, variant d1 (``preregistration.STEP_D``).

The 5-week mean inherited from the V2 does not say *when* it rained. d1 replaces it with non-overlapping windows
that end at the origin week o (the week that closes on ``origen_cierre``), for CHIRPS rainfall, ERA5-Land mean
temperature and ERA5-Land relative humidity:

    value of week o; mean of o-1..o-4; mean of o-5..o-8; mean of o-9..o-12   (12 columns)

plus, for the rainfall, the number of days with ``HEAVY_RAIN_MM`` or more in o-3..o and in o-7..o-4, counted on
the daily area-weighted polygon means that Earth Engine returned (bronze ``ee_final``, the same days the weekly
silver adds up). No Niño. Everything is computed in memory; nothing is written to ``data/``.

The daily bronze reader repeats ``chirps_ee.month_to_frame`` of ``feat/chirps-precipitation`` (not merged into this
branch); G35 checks that its weekly sums equal the silver.

Also here: the reported (non-deciding) metrics of step d: the Brier skill score against a climatology and the
AUPRC restricted to district-weeks below the outbreak threshold at the origin.
"""

import json
from datetime import datetime

import numpy as np
import pandas as pd

from denguekay.config.paths import BRONZE

import phase1b_prime as pb
import phase_b3_full_climate as b3
import phase_b_rain as pbr

EE_FINAL = BRONZE / "chirps" / "v3_sat" / "ee_final"
HEAVY_RAIN_MM = 20.0            # ETCCDI index R20mm: days with PRCP >= 20 mm
WINDOWS = {"s0": (0, 0), "media_s1_4": (1, 4), "media_s5_8": (5, 8), "media_s9_12": (9, 12)}
HEAVY_WINDOWS = {"s0_3": (0, 3), "s4_7": (4, 7)}
SOURCES = {"precip_total_mm": "chirps", "temp_media": "era5_land", "hum_rel_media": "era5_land"}
HEAVY_PREFIX = "dias_precip_20mm"
CLIMATOLOGY_HALF_WIDTH = 2       # epi weeks on each side of the target week (window of 5 weeks)


def window_column(source: str, window: str) -> str:
    return f"{source}_{window}"


def columns() -> list[str]:
    """The 14 columns of d1, in a fixed order."""
    return ([window_column(s, w) for s in SOURCES for w in WINDOWS]
            + [f"{HEAVY_PREFIX}_{w}" for w in HEAVY_WINDOWS])


# --- Daily CHIRPS from the Earth Engine bronze ----------------------------------------------------------------

def read_daily_ee(folder=EE_FINAL) -> pd.DataFrame:
    """Daily area-weighted means per district (``ubigeo``, ``fecha``, ``precip_mm``) of every saved monthly
    Earth Engine response ``AAAA/AAAA-MM.json`` (read only)."""
    files = sorted(folder.glob("*/????-??.json"))
    if not files:
        raise FileNotFoundError(f"No hay respuestas mensuales en {folder}")
    rows = []
    for f in files:
        response = json.loads(f.read_text(encoding="utf-8"))
        features = response.get("features", []) if isinstance(response, dict) else list(response)
        for feature in features:
            props = feature.get("properties", {})
            u = str(props.get("ubigeo"))
            for k, v in props.items():
                if k.startswith("p") and len(k) == 9 and k[1:].isdigit():
                    rows.append((u, datetime.strptime(k[1:], "%Y%m%d"), np.nan if v is None else float(v)))
    daily = pd.DataFrame(rows, columns=["ubigeo", "fecha", "precip_mm"])
    if not daily.ubigeo.str.fullmatch(r"\d{6}").all():
        raise ValueError("ubigeo no es un string de 6 dígitos")
    if daily.duplicated(["ubigeo", "fecha"]).any():
        raise ValueError("Días repetidos por distrito en el bronze de Earth Engine")
    return daily.sort_values(["ubigeo", "fecha"]).reset_index(drop=True)


def weekly_from_daily(daily: pd.DataFrame, threshold: float = HEAVY_RAIN_MM) -> pd.DataFrame:
    """MMWR weeks (Sunday to Saturday) with 7 days: weekly sum and number of days with ``>= threshold`` mm.
    A week with a missing day keeps both as NaN."""
    d = daily.copy()
    d["semana_inicio"] = pd.to_datetime(d.fecha).dt.to_period("W-SAT").dt.start_time
    d["fuerte"] = (d.precip_mm >= threshold).astype(float).where(d.precip_mm.notna())
    g = d.groupby(["ubigeo", "semana_inicio"])
    w = g.agg(n_dias=("fecha", "nunique"), suma=("precip_mm", lambda s: s.sum() if s.notna().all() else np.nan),
              dias_fuertes=("fuerte", lambda s: s.sum() if s.notna().all() else np.nan)).reset_index()
    return w[w.n_dias.eq(7)].drop(columns="n_dias").reset_index(drop=True)


# --- Windows per origin week ----------------------------------------------------------------------------------

def _check_regular(data: pd.DataFrame, what: str):
    gaps = data.groupby("ubigeo").semana_inicio.diff().dropna()
    if not gaps.eq(pd.Timedelta(days=7)).all():
        raise ValueError(f"La serie semanal de {what} tiene huecos o semanas repetidas")


def windows_by_origin_week(weekly: pd.DataFrame, value: str, windows: dict = WINDOWS, how: str = "mean",
                           prefix: str | None = None) -> pd.DataFrame:
    """Per district and origin week o: the aggregate (``mean`` or ``sum``) of ``value`` over weeks o-b..o-a of each
    window ``(a, b)``; NaN unless every week of the window has a value. Also the earliest and latest week used and,
    if ``weekly`` has ``fecha_disponible``, the latest one among all the weeks used."""
    data = weekly.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
    _check_regular(data, value)
    by = data.groupby("ubigeo")
    out = data[["ubigeo", "semana_inicio"]].rename(columns={"semana_inicio": "semana_origen"}).copy()
    prefix = prefix or value
    deepest = max(b for _, b in windows.values())
    for name, (a, b) in windows.items():
        width = b - a + 1
        rolled = by[value].transform(lambda s: getattr(s.rolling(width, min_periods=width), how)())
        out[f"{prefix}_{name}"] = rolled.groupby(data.ubigeo).shift(a)
    out[f"{prefix}_primera_semana"] = by.semana_inicio.shift(deepest)
    out[f"{prefix}_ultima_semana"] = data.semana_inicio
    if "fecha_disponible" in data:
        published = pd.to_datetime(data.fecha_disponible).groupby(data.ubigeo)
        out[f"{prefix}_publicada_max"] = pd.concat([published.shift(k) for k in range(deepest + 1)],
                                                   axis=1).max(axis=1)   # weeks before the series do not exist
    return out


def add_windows(origins: pd.DataFrame, by_week: pd.DataFrame) -> pd.DataFrame:
    """``origins`` (``origen_cierre`` is the Saturday of the origin week) plus every column of ``by_week``."""
    week = pd.to_datetime(origins.origen_cierre) - pd.Timedelta(days=6)
    key = pd.DataFrame({"ubigeo": origins.ubigeo.astype(str).to_numpy(), "semana_origen": week.to_numpy()})
    joined = key.merge(by_week, on=["ubigeo", "semana_origen"], how="left", validate="many_to_one")
    out = origins.copy()
    for c in by_week.columns.drop(["ubigeo", "semana_origen"]):
        out[c] = joined[c].to_numpy()
    return out


def build_d1(origins: pd.DataFrame, chirps: pd.DataFrame, era5: pd.DataFrame, weekly_daily: pd.DataFrame
             ) -> pd.DataFrame:
    """All the d1 columns on ``origins``.

    ``chirps``: weekly silver (``precip_total_mm``, ``fecha_disponible``); ``era5``: weekly ERA5-Land with
    ``temp_media`` and ``hum_rel_media``; ``weekly_daily``: ``weekly_from_daily`` of the Earth Engine bronze. The
    heavy-day counts take the ``fecha_disponible`` of the silver week (same days, same publication)."""
    out = add_windows(origins, windows_by_origin_week(chirps, "precip_total_mm"))
    for v in ("temp_media", "hum_rel_media"):
        out = add_windows(out, windows_by_origin_week(era5[["ubigeo", "semana_inicio", v]], v))
    heavy = weekly_daily[["ubigeo", "semana_inicio", "dias_fuertes"]].merge(
        chirps[["ubigeo", "semana_inicio", "fecha_disponible"]], on=["ubigeo", "semana_inicio"], how="inner",
        validate="one_to_one")
    return add_windows(out, windows_by_origin_week(heavy, "dias_fuertes", HEAVY_WINDOWS, how="sum",
                                                   prefix=HEAVY_PREFIX))


def era5_weekly(panel_2017: pd.DataFrame) -> pd.DataFrame:
    """Weekly ERA5-Land ``temp_media`` and ``hum_rel_media`` with ``ubigeo`` (the silvers of 1b' and b3)."""
    t = b3.era5_land_temperature(panel_2017)
    h = pb.era5_land_panel(panel_2017)
    return t.merge(h, on=["ubigeo", "semana_inicio"], how="outer", validate="one_to_one")


# --- Guards ---------------------------------------------------------------------------------------------------

def _max_diff(a, b) -> tuple[bool, float]:
    a, b = np.asarray(a, float), np.asarray(b, float)
    same_nan = bool(np.array_equal(np.isnan(a), np.isnan(b)))
    ok = ~np.isnan(a) & ~np.isnan(b)
    return same_nan, float(np.max(np.abs(a[ok] - b[ok]))) if ok.any() else 0.0


def guard_daily_matches_silver(weekly_daily: pd.DataFrame, chirps: pd.DataFrame, tol: float = 1e-9) -> dict:
    """G35a: the weekly sums of the daily Earth Engine bronze equal ``precip_total_mm`` of the silver, on the same
    weeks (so the heavy-day counts come from exactly the days that make the silver)."""
    both = chirps[["ubigeo", "semana_inicio", "precip_total_mm"]].merge(
        weekly_daily, on=["ubigeo", "semana_inicio"], how="outer", indicator=True)
    only = both._merge.value_counts().to_dict()
    inner = both[both._merge.eq("both")]
    same_nan, diff = _max_diff(inner.precip_total_mm, inner.suma)
    missing_in_daily = int(only.get("left_only", 0))
    return {"semanas_silver": len(chirps), "semanas_solo_en_silver": missing_in_daily,
            "semanas_solo_en_diario": int(only.get("right_only", 0)), "mismos_vacios": same_nan,
            "diferencia_maxima_mm": diff, "pasa": bool(missing_in_daily == 0 and same_nan and diff <= tol)}


def guard_consistency(origins: pd.DataFrame, tol: float = 1e-9) -> dict:
    """G35b: for each source, (week o + 4 · mean of o-1..o-4) / 5 equals the 5-week mean already validated
    (G25 rainfall, G17 humidity, G30 temperature) on every origin."""
    reference = {"precip_total_mm": pbr.COLUMN, "temp_media": b3.TEMP_COLUMN, "hum_rel_media": pb.COLUMN}
    out = {}
    for source, ref in reference.items():
        five = (origins[window_column(source, "s0")] + 4 * origins[window_column(source, "media_s1_4")]) / 5
        same_nan, diff = _max_diff(five, origins[ref])
        out[source] = {"columna_referencia": ref, "mismos_vacios": same_nan, "diferencia_maxima": diff,
                       "pasa": bool(same_nan and diff <= tol)}
    return {"por_fuente": out, "pasa": all(v["pasa"] for v in out.values())}


def guard_no_leakage_real(origins: pd.DataFrame, chirps: pd.DataFrame, era5: pd.DataFrame,
                          weekly_daily: pd.DataFrame, cut: str) -> dict:
    """G36 on the real data: change every weather value of the weeks after ``cut`` (rainfall, heavy days,
    temperature, humidity); no d1 column of an origin whose week is ``<= cut`` changes."""
    cut = pd.Timestamp(cut)
    base = build_d1(origins, chirps, era5, weekly_daily)

    def alter(df, cols):
        df = df.copy()
        later = pd.to_datetime(df.semana_inicio) > cut
        for c in cols:
            df.loc[later, c] = df.loc[later, c] * 3 + 11
        return df

    other = build_d1(origins, alter(chirps, ["precip_total_mm"]), alter(era5, ["temp_media", "hum_rel_media"]),
                     alter(weekly_daily, ["dias_fuertes"]))
    early = (pd.to_datetime(origins.origen_cierre) - pd.Timedelta(days=6)) <= cut
    cols = columns()
    a, b = base.loc[early, cols].to_numpy(float), other.loc[early, cols].to_numpy(float)
    unchanged = bool(np.array_equal(a, b, equal_nan=True))
    later_changed = int((~np.isclose(base.loc[~early, cols].to_numpy(float), other.loc[~early, cols].to_numpy(float),
                                     equal_nan=True)).any(axis=1).sum())
    return {"corte": str(cut.date()), "origenes_hasta_el_corte": int(early.sum()), "sin_cambios": unchanged,
            "origenes_posteriores_que_cambian": later_changed, "pasa": bool(unchanged and later_changed > 0)}


def guard_coverage(origins: pd.DataFrame, since: str = "2005-01-01") -> dict:
    """G37: every origin since 2005 has the 14 columns of d1."""
    return pbr.guard_coverage(origins, columns(), since)


def guard_availability(origins: pd.DataFrame, reference_days: int = pbr.REFERENCE_DAYS,
                       era5_delay_days: int = b3.ERA5_LAND_DELAY_DAYS) -> dict:
    """G38: CHIRPS windows and heavy-day counts use weeks with ``fecha_disponible`` <= origen_cierre +
    ``reference_days``; ERA5-Land windows use weeks whose Saturday + ``era5_delay_days`` <= origen_cierre +
    ``reference_days`` (the latest week used is always the origin week)."""
    close = pd.to_datetime(origins.origen_cierre)
    limit = close + pd.Timedelta(days=reference_days)
    out = {}
    for prefix in ("precip_total_mm", HEAVY_PREFIX):
        has = origins[[c for c in columns() if c.startswith(prefix)]].notna().any(axis=1)
        published = pd.to_datetime(origins.loc[has, f"{prefix}_publicada_max"])
        late = published > limit[has]
        out[prefix] = {"origenes": int(has.sum()), "sin_fecha_disponible": int(published.isna().sum()),
                       "afectados": int(late.sum()), "afectados_contra_origen_cierre": int((published > close[has]).sum()),
                       "margen_minimo_dias": int((limit[has] - published).dt.days.min()) if has.any() else None,
                       "pasa": bool(not late.any() and published.notna().all())}
    for source in ("temp_media", "hum_rel_media"):
        has = origins[[window_column(source, w) for w in WINDOWS]].notna().any(axis=1)
        published = pd.to_datetime(origins.loc[has, f"{source}_ultima_semana"]) + pd.Timedelta(days=6 + era5_delay_days)
        late = published > limit[has]
        out[source] = {"origenes": int(has.sum()), "afectados": int(late.sum()),
                       "afectados_contra_origen_cierre": int((published > close[has]).sum()), "pasa": bool(not late.any())}
    return {"referencia": f"origen_cierre + {reference_days} días (hipótesis)", "por_fuente": out,
            "pasa": all(v["pasa"] for v in out.values())}


def heavy_rain_frequency(daily: pd.DataFrame, thresholds=(10.0, 20.0, 30.0), first: str = "2005-01-01",
                         last: str = "2025-12-31") -> pd.DataFrame:
    """Reading for the threshold (data only, no model): days per year with ``>= threshold`` mm per district."""
    d = daily[(daily.fecha >= first) & (daily.fecha <= last)]
    years = d.fecha.dt.year.nunique()
    rows = []
    for t in thresholds:
        hit = d.precip_mm >= t
        per_year = hit.groupby(d.ubigeo).sum() / years
        years_with = d.assign(y=d.fecha.dt.year, g=hit).groupby(["ubigeo", "y"]).g.any().groupby("ubigeo").sum()
        rows.append({"umbral_mm": t, "dias_por_anio_mediana": float(per_year.median()),
                     "dias_por_anio_min": float(per_year.min()), "dias_por_anio_max": float(per_year.max()),
                     "distritos_con_dias_en_5_o_menos_anios": int((years_with <= 5).sum()), "anios": years})
    return pd.DataFrame(rows)


# --- Reported metrics (they do not decide) --------------------------------------------------------------------

def _circular_week_distance(a: np.ndarray, b: np.ndarray, n: int = 52) -> np.ndarray:
    d = np.abs(a - b)
    return np.minimum(d, n - d)


def climatology(pred: pd.DataFrame, series: pd.DataFrame, half_width: int = CLIMATOLOGY_HALF_WIDTH) -> pd.Series:
    """Out-of-sample climatological probability for every row of ``pred`` (one horizon and block per group).

    For a block, the labels available are those of the label series (2005 onwards) closed by the block's first
    origin (``semana_inicio`` + 6 days <= ``protocol.block_cutoff``), as for the calibrator. The probability of a
    row is the outbreak frequency of the same district in the epi weeks within ``half_width`` of the target's
    epi week (circular over 52 weeks; week 53 counts as 52); a district without such rows takes the frequency of
    all districts in those weeks."""
    from denguekay.evaluation import protocol as pa

    s = series.copy()
    s["semana_inicio"] = pd.to_datetime(s.semana_inicio)
    s["ubigeo"] = s.ubigeo.astype(str)
    s["sem_epi"] = s.semana.clip(upper=52)
    out = pd.Series(np.nan, index=pred.index, dtype=float)
    p = pred.copy()
    p["semana_inicio"] = pd.to_datetime(p.semana_inicio)
    p["origen_cierre"] = pd.to_datetime(p.origen_cierre)
    p["ubigeo"] = p.ubigeo.astype(str)
    target_week = p[["ubigeo", "semana_inicio"]].merge(s[["ubigeo", "semana_inicio", "sem_epi"]], how="left",
                                                       on=["ubigeo", "semana_inicio"], validate="many_to_one").sem_epi
    p["sem_epi"] = target_week.to_numpy()
    for (_, _), g in p.groupby(["horizonte", "bloque"]):
        cutoff = pa.block_cutoff(g)
        hist = s[(s.semana_inicio + pd.Timedelta(days=6)) <= cutoff]
        if hist.empty:
            continue
        weeks = np.arange(1, 53)
        near = _circular_week_distance(hist.sem_epi.to_numpy()[:, None], weeks[None, :]) <= half_width
        y = hist.brote.to_numpy(float)[:, None]
        by_district = {}
        for u, idx in hist.groupby("ubigeo").indices.items():
            n = near[idx].sum(axis=0)
            by_district[u] = np.where(n > 0, (near[idx] * y[idx]).sum(axis=0) / np.maximum(n, 1), np.nan)
        all_n = near.sum(axis=0)
        overall = np.where(all_n > 0, (near * y).sum(axis=0) / np.maximum(all_n, 1), np.nan)
        wk = g.sem_epi.to_numpy(int) - 1
        vals = np.array([by_district.get(u, np.full(52, np.nan))[w] for u, w in zip(g.ubigeo, wk)])
        out.loc[g.index] = np.where(np.isnan(vals), overall[wk], vals)
    return out


def reported_metrics(data: pd.DataFrame, clim: pd.Series, blocks) -> pd.DataFrame:
    """Per horizon and block of ``blocks``, on the protocol's ``datos`` (calibrated probability): Brier, Brier of
    the climatology, Brier skill score, AUPRC, and the AUPRC restricted to rows with ``persistencia`` <
    ``umbral_brote_casos`` (with their rows and positives)."""
    from sklearn.metrics import average_precision_score

    d = data.assign(clim=clim.reindex(data.index).to_numpy())
    rows = []
    for (h, block), g in d[d.bloque.isin(list(blocks))].groupby(["horizonte", "bloque"]):
        y, p = g.brote.to_numpy(int), g.probabilidad_calibrada.to_numpy(float)
        brier = float(np.mean((p - y) ** 2))
        brier_clim = float(np.mean((g.clim.to_numpy(float) - y) ** 2))
        below = g.persistencia.to_numpy(float) < g.umbral_brote_casos.to_numpy(float)
        yb = y[below]
        rows.append({"horizonte": h, "bloque": block, "n": len(g), "positivos": int(y.sum()),
                     "brier": brier, "brier_climatologia": brier_clim,
                     "bss_climatologia": 1 - brier / brier_clim if brier_clim > 0 else np.nan,
                     "auprc": float(average_precision_score(y, p)) if y.any() else np.nan,
                     "n_bajo_umbral": int(below.sum()), "positivos_bajo_umbral": int(yb.sum()),
                     "auprc_bajo_umbral": float(average_precision_score(yb, p[below])) if yb.any() else np.nan})
    return pd.DataFrame(rows)


# --- Run helpers (notebook 14) --------------------------------------------------------------------------------

def read_b3_predictions() -> dict[int, pd.DataFrame]:
    """Saved b3 predictions per seed (``models/experimentos/mejora_modelo/paso_b3/``, notebook 13)."""
    import phase3_onsets as p3

    path = p3.OUTPUT_DIR.parent / "paso_b3" / "predicciones_b3.csv.gz"
    saved = pd.read_csv(path, dtype={"ubigeo": "string"}, float_precision="round_trip")
    saved["ubigeo"] = saved.ubigeo.astype(object)
    return {int(s): g.drop(columns="semilla").reset_index(drop=True) for s, g in saved.groupby("semilla")}


def brier_compare(candidate: dict, reference: dict) -> dict:
    """Criterion (c): ``decide_step_d_brier`` over the 5 deciding seasons (seed medians, tie threshold = seed
    ranges of both, lead time of seed 17 as in ``phase3_onsets.compare``)."""
    import preregistration as pr
    from denguekay.evaluation import protocol as pa

    blocks = [pr.block_name(s) for s in pr.DECIDING_SEASONS]
    med = [pa.seed_median([e["metricas"] for e in v["evaluaciones"].values()]) for v in (candidate, reference)]
    ranges = pa.tie_threshold(*(pa.seed_ranges([e["metricas"] for e in v["evaluaciones"].values()])
                                for v in (candidate, reference)))
    seed = pr.SEEDS[0]
    lead = pr.lead_time_difference_multi(candidate["evaluaciones"][seed]["antelacion"],
                                         reference["evaluaciones"][seed]["antelacion"], "alerta_050")
    verdict = pr.decide_step_d_brier(*(m[m.bloque.isin(blocks)] for m in med), ranges[ranges.bloque.isin(blocks)], lead)
    return {"veredicto": verdict, "umbral_empate": ranges[ranges.bloque.isin(blocks)]}


def reported_by_variant(variant: dict, series: pd.DataFrame, blocks) -> pd.DataFrame:
    """``reported_metrics`` per seed on the protocol's ``datos`` and their median over the seeds."""
    per_seed = []
    for seed, e in variant["evaluaciones"].items():
        data = e["datos"]
        per_seed.append(reported_metrics(data, climatology(data, series), blocks).assign(semilla=seed))
    every = pd.concat(per_seed, ignore_index=True)
    return every.drop(columns="semilla").groupby(["horizonte", "bloque"]).median().reset_index()
