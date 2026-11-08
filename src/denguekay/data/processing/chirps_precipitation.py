"""
Bronze CHIRPS v3 -> weekly precipitation per district, with its availability date.

Study 06 (step b-V) builds the silver from the area-weighted polygon means: the final from Earth Engine
(``daily_final_from_ee``) and the CHC preliminary for the days without final (``daily_prelim_from_bronze``);
see the functions at the end. The centroid functions below are the earlier approach, kept for notebook 03c.

- Each district takes the pixel of its centroid (the same lat/lon of data/reference/distritos_piura_coords.csv
  that Open-Meteo uses). -9999 (sea / no data) becomes NaN, never 0.
- Weeks: the MMWR aggregation of ``weekly_aggregation.aggregate_available_to_weekly`` (only 7-day weeks; a
  week with no data stays empty).
- ``fecha_disponible``: the day the preliminary product covering the week's Saturday can be counted on.
  CHIRPS publishes preliminary pentads (days 1-5, 6-10, 11-15, 16-20, 21-25, 26-end of month) two days after
  each pentad ends, on the 2nd, 7th, 12th, 17th, 22nd and 27th (https://www.chc.ucsb.edu/data/chirps3). The
  listing dates of daily/prelim/sat/ for 2025-2026 (130 pentads) gave a lag after the pentad end of median 2,
  p90 4 and maximum 18 days; 5 days covers 94 % of those pentads (all of 2026), so the availability date is the
  pentad end plus 5 days. Larger delays are handled in the serving design. A model may use a week only from
  that date (the guard of the study's variant b).
"""

from pathlib import Path

import numpy as np
import pandas as pd

from denguekay.data.ingestion.chirps import NODATA, centroid_cells
from denguekay.data.processing.weekly_aggregation import aggregate_available_to_weekly

PUBLICATION_LAG_DAYS = 5        # conservative: CHC's own schedule is pentad end + 2 (OFFICIAL_LAG_DAYS)
OFFICIAL_LAG_DAYS = 2


def daily_from_bronze(folder: Path, districts: pd.DataFrame) -> pd.DataFrame:
    """Daily precipitation at each district centroid from every saved window of ``folder`` (AAAA/*.tif)."""
    import rasterio

    rows = []
    transform0 = None
    for f in sorted(folder.glob("*/chirps-v3.0.sat.*.tif")):
        day = pd.Timestamp(f.stem.removeprefix("chirps-v3.0.sat.").replace(".", "-"))
        with rasterio.open(f) as dataset:
            data = dataset.read(1)
            transform = dataset.transform
        if transform0 is None:
            transform0, (r, c) = transform, centroid_cells(transform, districts)
            if (r < 0).any() or (c < 0).any() or (r >= data.shape[0]).any() or (c >= data.shape[1]).any():
                raise ValueError("Hay centroides fuera de la ventana guardada")
        elif transform != transform0:
            raise ValueError(f"La ventana de {f.name} no coincide con la del primer día")
        values = data[r, c].astype(float)
        values[values == NODATA] = np.nan
        rows.append(pd.DataFrame({"id_distrito": districts.id_distrito.to_numpy(), "time": day,
                                  "precipitation_sum": values}))
    if not rows:
        raise FileNotFoundError(f"No hay ventanas de CHIRPS en {folder}")
    return pd.concat(rows, ignore_index=True)


def pentad_publication(day: pd.Series, lag_days: int = PUBLICATION_LAG_DAYS) -> pd.Series:
    """Availability date of the preliminary pentad that contains each day: its last day plus ``lag_days``."""
    day = pd.to_datetime(day)
    end_day = np.select([day.dt.day <= 5, day.dt.day <= 10, day.dt.day <= 15, day.dt.day <= 20, day.dt.day <= 25],
                        [5, 10, 15, 20, 25], default=day.dt.days_in_month)
    pentad_end = pd.to_datetime(dict(year=day.dt.year, month=day.dt.month, day=end_day))
    return pentad_end + pd.Timedelta(days=lag_days)


def weekly_precipitation(daily: pd.DataFrame, districts: pd.DataFrame) -> pd.DataFrame:
    """Weekly ``precip_total_mm`` per district (NaN-safe) with ``fecha_disponible`` of the week."""
    weekly = aggregate_available_to_weekly(daily, districts, ["precipitation_sum"])
    saturday = pd.to_datetime(weekly.semana_inicio) + pd.Timedelta(days=6)
    weekly["fecha_disponible"] = pentad_publication(saturday).to_numpy()
    return weekly


def weeks_published_after(weekly: pd.DataFrame, origins: pd.DataFrame, week_column: str = "semana_inicio") -> int:
    """How many (origin, week) pairs use a week published after the origin's ``origen_cierre`` (must be 0)."""
    published = weekly[["semana_inicio", "fecha_disponible"]].drop_duplicates().rename(
        columns={"semana_inicio": week_column})
    pairs = origins[["origen_cierre", week_column]].merge(published, on=week_column, how="left")
    return int((pd.to_datetime(pairs.fecha_disponible) > pd.to_datetime(pairs.origen_cierre)).sum())


# --- Silver from the polygon means: final (Earth Engine) + preliminary (CHC), study 06 step b-V ---------------

SILVER_COLUMNS = ["ubigeo", "semana_inicio", "precip_total_mm", "version", "fecha_disponible"]


def daily_final_from_ee(folder: Path) -> pd.DataFrame:
    """Daily area-weighted means of every saved monthly Earth Engine response (``AAAA/AAAA-MM.json``)."""
    import json

    from denguekay.data.ingestion.chirps_ee import month_to_frame

    files = sorted(folder.glob("*/????-??.json"))
    if not files:
        raise FileNotFoundError(f"No hay respuestas mensuales en {folder}")
    frames = [month_to_frame(json.loads(f.read_text(encoding="utf-8"))) for f in files]
    return pd.concat(frames, ignore_index=True).assign(version="final")


def daily_prelim_from_bronze(folder: Path, districts) -> pd.DataFrame:
    """Daily area-weighted means of the saved preliminary windows, with the function validated in the guard (b)
    of b-IV (``chirps_ee.local_district_means``). Every window must share the same grid."""
    import rasterio

    from denguekay.data.ingestion.chirps_ee import local_district_means

    windows, transform = {}, None
    for f in sorted(folder.glob("*/chirps-v3.0.prelim.*.tif")):
        day = pd.Timestamp(f.stem.removeprefix("chirps-v3.0.prelim.").replace(".", "-")).date()
        with rasterio.open(f) as ds:
            windows[day] = ds.read(1)
            t = tuple(ds.transform)[:6]
        if transform is not None and t != transform:
            raise ValueError(f"La ventana de {f.name} no coincide con la del primer día")
        transform = t
    if not windows:
        return pd.DataFrame(columns=["ubigeo", "fecha", "precip_mm", "version"])
    return local_district_means(windows, transform, districts).assign(version="prelim")


def combine_daily(final: pd.DataFrame, prelim: pd.DataFrame) -> pd.DataFrame:
    """Final wherever it exists; the preliminary only for days without final."""
    final_days = set(pd.to_datetime(final["fecha"]).dt.date)
    keep = prelim[~pd.to_datetime(prelim["fecha"]).dt.date.isin(final_days)] if len(prelim) else prelim
    daily = pd.concat([final, keep], ignore_index=True)
    daily["ubigeo"] = daily["ubigeo"].astype(str)
    if daily.duplicated(["ubigeo", "fecha"]).any():
        raise ValueError("Hay días repetidos por distrito.")
    return daily


def weekly_by_version(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """MMWR weeks (Sunday to Saturday) of 7 complete days from a single version.

    Returns the silver (``SILVER_COLUMNS``; a week with a missing value keeps ``precip_total_mm`` NaN) and the
    weeks left out (fewer than 7 days, or days of both versions), so that the report can list them."""
    d = daily.copy()
    d["fecha"] = pd.to_datetime(d["fecha"])
    d["semana_inicio"] = d["fecha"].dt.to_period("W-SAT").dt.start_time
    g = d.groupby(["ubigeo", "semana_inicio"])
    weekly = g.agg(precip_total_mm=("precip_mm", lambda s: s.sum() if s.notna().all() else np.nan),
                   n_dias=("fecha", "nunique"), n_versiones=("version", "nunique"),
                   version=("version", "first")).reset_index()
    ok = (weekly["n_dias"] == 7) & (weekly["n_versiones"] == 1)
    left_out = weekly.loc[~ok, ["ubigeo", "semana_inicio", "n_dias", "n_versiones"]].reset_index(drop=True)
    weekly = weekly[ok].copy()
    saturday = weekly["semana_inicio"] + pd.Timedelta(days=6)
    weekly["fecha_disponible"] = pentad_publication(saturday).dt.strftime("%Y-%m-%d").to_numpy()
    weekly["semana_inicio"] = weekly["semana_inicio"].dt.strftime("%Y-%m-%d")
    weekly["ubigeo"] = weekly["ubigeo"].astype(str)
    weekly = weekly[SILVER_COLUMNS].sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
    return weekly, left_out


def write_silver(weekly: pd.DataFrame, path: Path) -> Path:
    """Write the silver CSV (temporary name, then rename). Never overwrites."""
    import os

    if path.exists():
        raise FileExistsError(f"Ya existe {path}: no se sobrescribe.")
    tmp = path.with_suffix(".tmp")
    weekly.to_csv(tmp, index=False, encoding="utf-8")
    os.replace(tmp, path)
    return path


def combine_daily_by_week(final: pd.DataFrame, prelim: pd.DataFrame) -> pd.DataFrame:
    """One version per MMWR week (decision of 2026-11-06): a week whose 7 days all have final takes the final;
    otherwise it takes the preliminary for its 7 days (a week with final on some days and preliminary on the rest,
    such as the one of 2026-09-27, is all preliminary). Days of a week with neither complete stay as they come, so
    ``weekly_by_version`` lists that week as left out."""
    frames = []
    for name, d in (("final", final), ("prelim", prelim)):
        d = d.copy()
        d["fecha"] = pd.to_datetime(d["fecha"])
        d["ubigeo"] = d["ubigeo"].astype(str)
        d["semana_inicio"] = d["fecha"].dt.to_period("W-SAT").dt.start_time
        frames.append(d)
    f, p = frames
    complete = lambda d: d.groupby(["ubigeo", "semana_inicio"]).fecha.nunique().eq(7)
    f_ok, p_ok = complete(f), complete(p)
    f_weeks = set(f_ok[f_ok].index)
    p_weeks = set(p_ok[p_ok].index) - f_weeks
    key = lambda d: pd.Series(list(zip(d.ubigeo, d.semana_inicio)), index=d.index)
    fk, pk = key(f), key(p)
    use_f = f[fk.map(lambda k: k not in p_weeks)]               # complete final weeks, and incomplete ones
    final_weeks_any = set(fk)
    use_p = p[pk.map(lambda k: k in p_weeks or k not in final_weeks_any)]   # complete prelim weeks without final
    daily = pd.concat([use_f, use_p], ignore_index=True).drop(columns="semana_inicio")
    daily["fecha"] = daily["fecha"].dt.date
    if daily.duplicated(["ubigeo", "fecha"]).any():
        raise ValueError("Hay días repetidos por distrito.")
    return daily.sort_values(["ubigeo", "fecha"]).reset_index(drop=True)


def daily_from_windows(folder: Path, districts, version: str, pattern: str) -> pd.DataFrame:
    """Daily area-weighted means (``chirps_ee.local_district_means``) of the saved Piura windows in
    ``folder/AAAA/``; when a day has revisions (``folder/AAAA/<fecha_descarga>/``), the latest one is used. Every
    window must share the same grid."""
    import rasterio

    from denguekay.data.ingestion.chirps_ee import local_district_means

    latest = {}
    for f in sorted(folder.glob(f"*/{pattern}")) + sorted(folder.glob(f"*/*/{pattern}")):
        day = pd.Timestamp(f.stem[-10:].replace(".", "-")).date()
        stamp = "" if f.parent.parent == folder else f.parent.name
        if day not in latest or stamp > latest[day][0]:
            latest[day] = (stamp, f)
    windows, transform = {}, None
    for day, (_, f) in sorted(latest.items()):
        with rasterio.open(f) as ds:
            windows[day] = ds.read(1)
            t = tuple(ds.transform)[:6]
        if transform is not None and t != transform:
            raise ValueError(f"La ventana de {f.name} no coincide con la del primer día")
        transform = t
    if not windows:
        return pd.DataFrame(columns=["ubigeo", "fecha", "precip_mm", "version"])
    return local_district_means(windows, transform, districts).assign(version=version)
