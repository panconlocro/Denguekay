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
