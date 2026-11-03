"""Phase 1b consistency check: weather already downloaded (default model) versus one fixed model.

Read-only: it reads two caches of data/bronze/meteo/ that the team downloads with the pipeline and
compares them in the weeks both share (2017-2025). It never downloads nor writes in data/.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from denguekay.config.paths import CACHE_METEO, CACHE_METEO_ERA5_2017_2025, DISTRICT_COORDS
from denguekay.data.processing.weekly_aggregation import WEEKLY_RENAME, aggregate_to_weekly, load_daily_from_cache

WEEKLY_VARIABLES = [v for k, v in WEEKLY_RENAME.items() if k != "time"]
KEY = ["id_distrito", "semana_inicio"]


def weekly_from_cache(cache_dir: Path, districts: pd.DataFrame) -> pd.DataFrame:
    """Weekly weather of one cache with the same aggregation as notebook 03."""
    daily = load_daily_from_cache(expected_districts=len(districts), cache_dir=cache_dir)
    return aggregate_to_weekly(daily, districts, include_id=True)


def paired(current: pd.DataFrame, fixed: pd.DataFrame) -> pd.DataFrame:
    """Weeks present in both caches, with ``<variable>_actual`` and ``<variable>_fijo`` columns."""
    cols = KEY + ["anio"] + WEEKLY_VARIABLES
    both = current[cols].merge(fixed[KEY + WEEKLY_VARIABLES], on=KEY, how="inner", suffixes=("_actual", "_fijo"))
    return both


def compare(both: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    """
    Per variable (and optional grouping): rows, mean difference fixed - current, MAE, max |difference|,
    Pearson correlation and share of weeks with exactly the same value.
    """
    rows = []
    groups = both.groupby(by) if by else [((), both)]
    for key, g in groups:
        key = key if isinstance(key, tuple) else (key,)
        for v in WEEKLY_VARIABLES:
            a, f = g[f"{v}_actual"].to_numpy(float), g[f"{v}_fijo"].to_numpy(float)
            ok = ~(np.isnan(a) | np.isnan(f))
            d = f[ok] - a[ok]
            corr = np.corrcoef(a[ok], f[ok])[0, 1] if ok.sum() > 1 and a[ok].std() > 0 and f[ok].std() > 0 else np.nan
            rows.append({**dict(zip(by or [], key)), "variable": v, "filas": int(ok.sum()),
                         "nulos": int((~ok).sum()), "media_actual": float(a[ok].mean()) if ok.any() else np.nan,
                         "diferencia_media": float(d.mean()) if ok.any() else np.nan,
                         "mae": float(np.abs(d).mean()) if ok.any() else np.nan,
                         "max_abs": float(np.abs(d).max()) if ok.any() else np.nan,
                         "correlacion": float(corr), "iguales": float((d == 0).mean()) if ok.any() else np.nan})
    return pd.DataFrame(rows)


def coverage(current: pd.DataFrame, fixed: pd.DataFrame) -> dict:
    """Weeks only in one of the two caches (they must match before comparing)."""
    a, f = (set(map(tuple, x[KEY].astype(str).to_numpy())) for x in (current, fixed))
    return {"semanas_actual": len(a), "semanas_fijo": len(f), "solo_actual": len(a - f), "solo_fijo": len(f - a)}


def run_comparison(fixed_cache: Path = CACHE_METEO_ERA5_2017_2025, current_cache: Path = CACHE_METEO) -> dict:
    """Both caches -> coverage, per-variable summary and per-variable-and-year summary."""
    districts = pd.read_csv(DISTRICT_COORDS)
    current = weekly_from_cache(current_cache, districts)
    fixed = weekly_from_cache(fixed_cache, districts)
    both = paired(current, fixed)
    return {"cobertura": coverage(current, fixed), "por_variable": compare(both),
            "por_variable_anio": compare(both, by=["anio"]), "pares": both}


# ---------------------------------------------------------------------------
# Districts that share a grid cell or an identical weather series
# ---------------------------------------------------------------------------

ERA5_STEP = 0.25  # degrees


def nearest_era5_cell(districts: pd.DataFrame, step: float = ERA5_STEP) -> pd.DataFrame:
    """Nearest point of a regular ``step``° grid to each district centroid (a geometric approximation:
    Open-Meteo may pick a neighbouring cell with land and a similar elevation)."""
    out = districts[["id_distrito", "distrito", "lat", "lon"]].copy()
    out["lat_celda"] = (out.lat / step).round() * step
    out["lon_celda"] = (out.lon / step).round() * step
    return out


def cells_from_cache(cache_dir: Path) -> pd.DataFrame:
    """Grid cell the API reported per district (only caches downloaded with a fixed model keep it)."""
    rows = []
    for f in sorted(cache_dir.glob("distrito_*.parquet")):
        d = pd.read_parquet(f, columns=["id_distrito", "lat_celda", "lon_celda"])
        rows.append(d.iloc[0])
    return pd.DataFrame(rows).reset_index(drop=True)


def shared_cells(cells: pd.DataFrame) -> dict:
    """How many districts share a cell with another district, and the groups."""
    size = cells.groupby(["lat_celda", "lon_celda"]).id_distrito.transform("size")
    groups = (cells[size.gt(1)].groupby(["lat_celda", "lon_celda"]).id_distrito.apply(sorted).tolist())
    return {"distritos": len(cells), "celdas": int(cells.groupby(["lat_celda", "lon_celda"]).ngroups),
            "distritos_que_comparten": int(size.gt(1).sum()), "grupos": groups}


def identical_series(weekly: pd.DataFrame) -> dict:
    """Groups of districts whose whole weekly series (9 variables, every week) is identical."""
    wide = weekly.sort_values(KEY).groupby("id_distrito")[WEEKLY_VARIABLES].apply(
        lambda g: hash(g.to_numpy(float).tobytes()))
    groups = [sorted(ids) for ids in wide.groupby(wide).groups.values() if len(ids) > 1]
    groups = [sorted(int(i) for i in g) for g in groups]
    return {"distritos": int(len(wide)), "series_distintas": int(wide.nunique()),
            "distritos_con_serie_identica": int(sum(len(g) for g in groups)), "grupos": sorted(groups)}
