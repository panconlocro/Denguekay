"""Phase 1b': humidity of ERA5-Land 2000-2025 over L + 5a (``preregistration.PHASE1B_PRIME``).

H at an origin is the mean humidity of the 5 weeks that end with the origin week (the week that closes on
``origen_cierre``): the same value that gold calls ``hum_rel_media_media5_h2`` on the row of the h=2 target
(``features.climate.build_observed_climate``: rolling 5 weeks, shifted by the horizon). ``extra_lag`` moves the
window back whole weeks (for an availability rule).

ERA5-Land on Open-Meteo is updated "daily with 5 days delay" (https://open-meteo.com/en/docs/historical-weather-api):
a week is published ``ERA5_LAND_DELAY_DAYS`` after its Saturday.
"""

import numpy as np
import pandas as pd

from denguekay.config.paths import SILVER_METEO_ERA5_LAND_2000_2025

WINDOW = 5
ERA5_LAND_DELAY_DAYS = 5
COLUMN = "hum_rel_media_media5_h2"


def era5_land_panel(panel_2017: pd.DataFrame, path=SILVER_METEO_ERA5_LAND_2000_2025) -> pd.DataFrame:
    """Weekly ERA5-Land humidity with ``ubigeo``.

    Mapped by the district centroid (lat, lon): both silvers take it from data/reference/distritos_piura_coords.csv,
    while the meteo names are only fixed later, in the integrated panel (e.g. "El Carmendela Frontera").
    """
    weekly = pd.read_csv(path, parse_dates=["semana_inicio"], float_precision="round_trip")
    keys = panel_2017[["lat", "lon", "ubigeo"]].drop_duplicates()
    if keys[["lat", "lon"]].duplicated().any() or len(keys) != panel_2017.ubigeo.nunique():
        raise ValueError("lat/lon no identifican un único ubigeo")
    out = weekly.merge(keys, on=["lat", "lon"], how="left", validate="many_to_one")
    if out.ubigeo.isna().any():
        raise ValueError(f"Distritos sin ubigeo: {sorted(out.loc[out.ubigeo.isna(), 'distrito'].unique())}")
    if out.groupby("ubigeo").distrito.nunique().gt(1).any():
        raise ValueError("Un ubigeo recibió dos distritos")
    out["ubigeo"] = out.ubigeo.astype(str)
    return out[["ubigeo", "semana_inicio", "hum_rel_media"]].sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)


def humidity_by_origin_week(weekly: pd.DataFrame, extra_lag: int = 0, window: int = WINDOW) -> pd.DataFrame:
    """Per district and origin week: mean of the ``window`` weeks ending ``extra_lag`` weeks before it."""
    data = weekly.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
    gaps = data.groupby("ubigeo").semana_inicio.diff().dropna()
    if not gaps.eq(pd.Timedelta(days=7)).all():
        raise ValueError("La serie semanal de humedad tiene huecos o semanas repetidas")
    rolling = data.groupby("ubigeo").hum_rel_media.transform(lambda s: s.rolling(window, min_periods=window).mean())
    data["H"] = rolling.groupby(data.ubigeo).shift(extra_lag)
    data["ultima_semana_usada"] = data.groupby("ubigeo").semana_inicio.shift(extra_lag)
    return data.rename(columns={"semana_inicio": "semana_origen"})[["ubigeo", "semana_origen", "H", "ultima_semana_usada"]]


def add_humidity(origins: pd.DataFrame, by_week: pd.DataFrame, column: str = COLUMN) -> pd.DataFrame:
    """``origins`` (with ``origen_cierre``, a Saturday) plus H of their origin week as ``column``."""
    week = pd.to_datetime(origins.origen_cierre) - pd.Timedelta(days=6)
    key = pd.DataFrame({"ubigeo": origins.ubigeo.astype(str).to_numpy(), "semana_origen": week.to_numpy()})
    joined = key.merge(by_week, on=["ubigeo", "semana_origen"], how="left", validate="many_to_one")
    out = origins.copy()
    out[column] = joined.H.to_numpy()
    out["h_ultima_semana"] = joined.ultima_semana_usada.to_numpy()
    return out


def weeks_not_yet_published(origins: pd.DataFrame, delay_days: int = ERA5_LAND_DELAY_DAYS) -> int:
    """Origins whose H uses a week published after ``origen_cierre`` (week Saturday + ``delay_days``)."""
    saturday = pd.to_datetime(origins.h_ultima_semana) + pd.Timedelta(days=6)
    return int((saturday + pd.Timedelta(days=delay_days) > pd.to_datetime(origins.origen_cierre)).sum())


def guard_g17(gold: pd.DataFrame, panel_2017: pd.DataFrame) -> dict:
    """G17: H computed with the silver in use ("Best match") equals gold's hum_rel_media_media5_h2 exactly."""
    current = panel_2017[["ubigeo", "semana_inicio", "hum_rel_media"]].copy()
    current["ubigeo"] = current.ubigeo.astype(str)
    current["semana_inicio"] = pd.to_datetime(current.semana_inicio)
    by_week = humidity_by_origin_week(current)
    g = gold[["ubigeo", "semana_inicio", COLUMN]].copy()
    g["ubigeo"] = g.ubigeo.astype(str)
    g["semana_origen"] = pd.to_datetime(g.semana_inicio) - pd.Timedelta(days=14)   # h=2 target -> origin week
    both = g.merge(by_week, on=["ubigeo", "semana_origen"], how="left", validate="one_to_one")
    a, b = both[COLUMN].to_numpy(float), both.H.to_numpy(float)
    same_nan = np.array_equal(np.isnan(a), np.isnan(b))
    ok = ~np.isnan(a)
    diff = float(np.max(np.abs(a[ok] - b[ok]))) if ok.any() else 0.0
    return {"filas_gold": len(g), "con_valor": int(ok.sum()), "mismos_vacios": bool(same_nan),
            "diferencia_maxima": diff, "pasa": bool(same_nan and diff == 0.0)}


def guard_g19(origins: pd.DataFrame, column: str = COLUMN, since: str = "2005-01-01") -> dict:
    """G19: every origin since 2005 has H."""
    sel = pd.to_datetime(origins.origen_cierre) >= pd.Timestamp(since)
    missing = int(origins.loc[sel, column].isna().sum())
    return {"origenes_desde_2005": int(sel.sum()), "sin_H": missing, "pasa": missing == 0}
