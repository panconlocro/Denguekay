"""Climate step b, variant b3: the full climate over L + 5a (``preregistration.STEP_B3``).

b3 = C3 + humidity of ERA5-Land (H of 1b') + CHIRPS rainfall (b1) + mean temperature of ERA5-Land + Niño 1+2
(variable 4b of phase 4). The temperature is ``TEMP_COLUMN``: the mean of the weekly ``temp_media`` of the 5 weeks
that end with the origin week, the same alignment (h=2) and window as the humidity and the rainfall; it comes from
``data/silver/meteo_humedad_era5_land_2000_2025.csv`` (the ERA5-Land silver of 1b', which also has temp_media).
Gold has no temperature column, so its definition is checked against the gold function itself
(``features.climate.build_observed_climate`` with h=2) on the silver in use ("Best match").
"""

from pathlib import Path

import numpy as np
import pandas as pd

from denguekay.config.paths import BRONZE_ENSO, SILVER_METEO_ERA5_LAND_2000_2025

import phase1b_prime as pb
import phase_b_rain as pbr

TEMP_SOURCE = "temp_media"
TEMP_COLUMN = "temp_media_media5_h2"
NINO_COLUMN = "nino12_anom_media3"
RAW_ENSO_FILE = "sstoi_20261103.indices"
CHECK_MONTH = (2026, 10)
CHECK_ANOMALY = 5.25
# Publication delay of ERA5-Land on Open-Meteo measured by Rosa on 2026-11-06 (data up to 2026-10-31); 1b' used 5
ERA5_LAND_DELAY_DAYS = 7


def era5_land_temperature(panel_2017: pd.DataFrame, path=SILVER_METEO_ERA5_LAND_2000_2025) -> pd.DataFrame:
    """Weekly ERA5-Land mean temperature with ``ubigeo`` (mapped by centroid, as ``pb.era5_land_panel``)."""
    weekly = pd.read_csv(path, parse_dates=["semana_inicio"], float_precision="round_trip")
    keys = panel_2017[["lat", "lon", "ubigeo"]].drop_duplicates()
    if keys[["lat", "lon"]].duplicated().any() or len(keys) != panel_2017.ubigeo.nunique():
        raise ValueError("lat/lon no identifican un único ubigeo")
    out = weekly.merge(keys, on=["lat", "lon"], how="left", validate="many_to_one")
    if out.ubigeo.isna().any():
        raise ValueError(f"Distritos sin ubigeo: {sorted(out.loc[out.ubigeo.isna(), 'distrito'].unique())}")
    out["ubigeo"] = out.ubigeo.astype(str)
    return out[["ubigeo", "semana_inicio", TEMP_SOURCE]].sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)


def temperature_by_origin_week(weekly: pd.DataFrame, extra_lag: int = 0) -> pd.DataFrame:
    """Per district and origin week: mean temperature of the 5 weeks ending with it (``pbr.rain_by_origin_week``)."""
    return pbr.rain_by_origin_week(weekly.drop(columns="fecha_disponible", errors="ignore"), extra_lag=extra_lag,
                                   value=TEMP_SOURCE)


def add_temperature(origins: pd.DataFrame, by_week: pd.DataFrame) -> pd.DataFrame:
    """``origins`` plus ``TEMP_COLUMN`` and the last week it uses (``t_ultima_semana``)."""
    week = pd.to_datetime(origins.origen_cierre) - pd.Timedelta(days=6)
    key = pd.DataFrame({"ubigeo": origins.ubigeo.astype(str).to_numpy(), "semana_origen": week.to_numpy()})
    joined = key.merge(by_week, on=["ubigeo", "semana_origen"], how="left", validate="many_to_one")
    out = origins.copy()
    out[TEMP_COLUMN] = joined.R.to_numpy()
    out["t_ultima_semana"] = joined.ultima_semana_usada.to_numpy()
    return out


def guard_temperature_definition(panel_2017: pd.DataFrame) -> dict:
    """Definition: on the silver in use, the function equals ``build_observed_climate(h=2)`` of gold.py exactly
    (the value of origin week o sits on the row of target week o + 2)."""
    from denguekay.features.climate import build_observed_climate

    panel = panel_2017.copy()
    panel["ubigeo"] = panel.ubigeo.astype(str)
    panel["semana_inicio"] = pd.to_datetime(panel.semana_inicio)
    gold_like = build_observed_climate(panel, 2, variables=(TEMP_SOURCE,))
    by_week = temperature_by_origin_week(panel[["ubigeo", "semana_inicio", TEMP_SOURCE]])
    g = gold_like[["ubigeo", "semana_inicio", TEMP_COLUMN]].copy()
    g["semana_origen"] = pd.to_datetime(g.semana_inicio) - pd.Timedelta(days=14)
    both = g.merge(by_week, on=["ubigeo", "semana_origen"], how="left", validate="one_to_one")
    a, b = both[TEMP_COLUMN].to_numpy(float), both.R.to_numpy(float)
    same_nan = np.array_equal(np.isnan(a), np.isnan(b))
    ok = ~np.isnan(a)
    diff = float(np.max(np.abs(a[ok] - b[ok]))) if ok.any() else 0.0
    return {"filas": len(g), "con_valor": int(ok.sum()), "mismos_vacios": bool(same_nan), "diferencia_maxima": diff,
            "pasa": bool(same_nan and diff == 0.0)}


def guard_temperature_availability(origins: pd.DataFrame, reference_days: int = pbr.REFERENCE_DAYS,
                                   delay_days: int = ERA5_LAND_DELAY_DAYS) -> dict:
    """Availability: the last week used is published (its Saturday + ``delay_days``) by origen_cierre +
    ``reference_days``, in every origin with a value (same reference as the humidity in 1b')."""
    o = origins[origins[TEMP_COLUMN].notna()]
    published = pd.to_datetime(o.t_ultima_semana) + pd.Timedelta(days=6 + delay_days)
    close = pd.to_datetime(o.origen_cierre)
    late = published > close + pd.Timedelta(days=reference_days)
    return {"referencia": f"origen_cierre + {reference_days} días (hipótesis)", "origenes": len(o),
            "afectados": int(late.sum()), "afectados_contra_origen_cierre": int((published > close).sum()),
            "pasa": not late.any()}


def guard_raw_noaa(silver: pd.DataFrame, raw_path=None, month=CHECK_MONTH, expected=CHECK_ANOMALY) -> dict:
    """The Niño 1+2 anomaly of ``month`` in the raw NOAA CPC file equals ``expected`` and the silver."""
    from denguekay.data.processing.enso_index import parse_sstoi

    raw_path = raw_path or BRONZE_ENSO / RAW_ENSO_FILE
    raw = parse_sstoi(Path(raw_path).read_text(encoding="utf-8"))
    y, m = month
    raw_value = raw.loc[raw.anio.eq(y) & raw.mes.eq(m), "nino12_anom"]
    silver_value = silver.loc[silver.anio.eq(y) & silver.mes.eq(m), "nino12_anom"]
    if len(raw_value) != 1 or len(silver_value) != 1:
        return {"archivo": str(raw_path.name), "mes": f"{y}-{m:02d}", "pasa": False, "motivo": "mes ausente o repetido"}
    r, s = float(raw_value.iloc[0]), float(silver_value.iloc[0])
    return {"archivo": str(raw_path.name), "mes": f"{y}-{m:02d}", "crudo": r, "silver": s, "esperado": expected,
            "pasa": bool(r == expected and s == expected)}


def nino_training_range(origins: pd.DataFrame, since: str = "2005-01-01") -> dict:
    """Reading: range of ``NINO_COLUMN`` over the origins since 2005 (the training and evaluation origins)."""
    sel = pd.to_datetime(origins.origen_cierre) >= pd.Timestamp(since)
    v = origins.loc[sel, NINO_COLUMN]
    return {"minimo": float(v.min()), "maximo": float(v.max()), "origenes": int(sel.sum())}
