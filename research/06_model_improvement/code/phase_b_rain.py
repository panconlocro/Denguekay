"""Climate step b: CHIRPS v3 rainfall over L + 5a, variants b1 and b2 (``preregistration.STEP_B``).

The rainfall variable at an origin is the mean of the weekly CHIRPS rainfall (area-weighted polygon mean) of the
5 weeks that end with the origin week (the week that closes on ``origen_cierre``): the same definition that
gold calls ``precip_total_mm_media5_h2`` on the row of the h=2 target (A3 of the V2;
``features.climate.build_observed_climate``: rolling 5 weeks, shifted by the horizon). Only the source changes.

The silver ``precip_chirps_v3_semanal_desde_2000.csv`` (study 06, step b-V of ``feat/chirps-precipitation``) carries
``fecha_disponible`` per week (end of the preliminary pentad of the week's Saturday + 5 days). A week can be used
at an origin only if it is published by ``origen_cierre`` + ``REFERENCE_DAYS`` (Rosa's reference, a *hypothesis*:
the MINSA Situation Room runs about 3 weeks late).
"""

import numpy as np
import pandas as pd

from denguekay.config.paths import SILVER

# Written in step b-V on 2026-11-06 (final version from Earth Engine only, 2000-01-02 to 2026-09-20). The constant
# SILVER_CHIRPS_PRECIP lives in feat/chirps-precipitation; this branch does not merge it (not without Rosa).
SILVER_CHIRPS = SILVER / "precip_chirps_v3_semanal_desde_2000.csv"
WINDOW = 5
COLUMN = "precip_total_mm_media5_h2"
SOURCE_COLUMN = "precip_total_mm"
REFERENCE_DAYS = 14


def read_chirps(path=SILVER_CHIRPS) -> pd.DataFrame:
    """Weekly CHIRPS silver with ``ubigeo`` as a 6-digit string and dates parsed."""
    weekly = pd.read_csv(path, dtype={"ubigeo": str}, parse_dates=["semana_inicio", "fecha_disponible"],
                         float_precision="round_trip")
    if not weekly.ubigeo.str.fullmatch(r"\d{6}").all():
        raise ValueError("ubigeo no es un string de 6 dígitos")
    if weekly.duplicated(["ubigeo", "semana_inicio"]).any():
        raise ValueError("Semanas repetidas en el silver de CHIRPS")
    return weekly.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)


def rain_by_origin_week(weekly: pd.DataFrame, extra_lag: int = 0, window: int = WINDOW,
                        value: str = SOURCE_COLUMN) -> pd.DataFrame:
    """Per district and origin week: mean of the ``window`` weeks ending ``extra_lag`` weeks before it, the last
    week used and the latest ``fecha_disponible`` among the weeks used (if the silver has it)."""
    data = weekly.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
    gaps = data.groupby("ubigeo").semana_inicio.diff().dropna()
    if not gaps.eq(pd.Timedelta(days=7)).all():
        raise ValueError("La serie semanal de lluvia tiene huecos o semanas repetidas")
    by = data.groupby("ubigeo")
    rolling = by[value].transform(lambda s: s.rolling(window, min_periods=window).mean())
    data["R"] = rolling.groupby(data.ubigeo).shift(extra_lag)
    data["ultima_semana_usada"] = by.semana_inicio.shift(extra_lag)
    if "fecha_disponible" in data:
        published = pd.to_datetime(data.fecha_disponible).groupby(data.ubigeo)
        latest = pd.concat([published.shift(k) for k in range(window)], axis=1).max(axis=1, skipna=False)
        data["publicada_max"] = latest.groupby(data.ubigeo).shift(extra_lag)
    else:
        data["publicada_max"] = pd.NaT
    return data.rename(columns={"semana_inicio": "semana_origen"})[
        ["ubigeo", "semana_origen", "R", "ultima_semana_usada", "publicada_max"]]


def add_rain(origins: pd.DataFrame, by_week: pd.DataFrame, column: str = COLUMN) -> pd.DataFrame:
    """``origins`` (with ``origen_cierre``, a Saturday) plus the rainfall of their origin week as ``column``."""
    week = pd.to_datetime(origins.origen_cierre) - pd.Timedelta(days=6)
    key = pd.DataFrame({"ubigeo": origins.ubigeo.astype(str).to_numpy(), "semana_origen": week.to_numpy()})
    joined = key.merge(by_week, on=["ubigeo", "semana_origen"], how="left", validate="many_to_one")
    out = origins.copy()
    out[column] = joined.R.to_numpy()
    out["lluvia_ultima_semana"] = joined.ultima_semana_usada.to_numpy()
    out["lluvia_publicada_max"] = joined.publicada_max.to_numpy()
    return out


def guard_definition(gold: pd.DataFrame, panel_2017: pd.DataFrame) -> dict:
    """G25: the function, applied to the rainfall of the silver in use ("Best match"), reproduces gold's
    ``precip_total_mm_media5_h2`` exactly (same definition; only the source changes in b1 and b2)."""
    current = panel_2017[["ubigeo", "semana_inicio", SOURCE_COLUMN]].copy()
    current["ubigeo"] = current.ubigeo.astype(str)
    current["semana_inicio"] = pd.to_datetime(current.semana_inicio)
    by_week = rain_by_origin_week(current)
    g = gold[["ubigeo", "semana_inicio", COLUMN]].copy()
    g["ubigeo"] = g.ubigeo.astype(str)
    g["semana_origen"] = pd.to_datetime(g.semana_inicio) - pd.Timedelta(days=14)   # h=2 target -> origin week
    both = g.merge(by_week, on=["ubigeo", "semana_origen"], how="left", validate="one_to_one")
    a, b = both[COLUMN].to_numpy(float), both.R.to_numpy(float)
    same_nan = np.array_equal(np.isnan(a), np.isnan(b))
    ok = ~np.isnan(a)
    diff = float(np.max(np.abs(a[ok] - b[ok]))) if ok.any() else 0.0
    return {"filas_gold": len(g), "con_valor": int(ok.sum()), "mismos_vacios": bool(same_nan),
            "diferencia_maxima": diff, "pasa": bool(same_nan and diff == 0.0)}


def guard_availability(origins: pd.DataFrame, reference_days: int = REFERENCE_DAYS) -> dict:
    """G27 (type G21): no origin uses a week whose ``fecha_disponible`` is after ``origen_cierre`` +
    ``reference_days`` (complete table). Also counts, for the report, against ``origen_cierre`` alone."""
    with_value = origins[origins[COLUMN].notna()]
    published = pd.to_datetime(with_value.lluvia_publicada_max)
    close = pd.to_datetime(with_value.origen_cierre)
    late = published > close + pd.Timedelta(days=reference_days)
    margin = (close + pd.Timedelta(days=reference_days) - published).dt.days
    return {"referencia": f"origen_cierre + {reference_days} días (hipótesis)", "origenes_con_lluvia": len(with_value),
            "sin_fecha_disponible": int(published.isna().sum()), "afectados": int(late.sum()),
            "afectados_contra_origen_cierre": int((published > close).sum()),
            "margen_minimo_dias": int(margin.min()) if len(margin) else None,
            "pasa": bool(not late.any() and published.notna().all())}


def guard_coverage(origins: pd.DataFrame, columns=(COLUMN,), since: str = "2005-01-01") -> dict:
    """G28: every origin since 2005 has the variant's climate columns."""
    sel = pd.to_datetime(origins.origen_cierre) >= pd.Timestamp(since)
    missing = int(origins.loc[sel, list(columns)].isna().any(axis=1).sum())
    return {"origenes_desde_2005": int(sel.sum()), "sin_valor": missing, "pasa": missing == 0}


def versions_used(origins: pd.DataFrame, weekly: pd.DataFrame) -> dict:
    """Reading: versions of the weeks that reach the origins (training uses the final; b-VI measures the gap)."""
    used = origins[origins[COLUMN].notna()]
    last = used[["ubigeo", "lluvia_ultima_semana"]].rename(columns={"lluvia_ultima_semana": "semana_inicio"})
    v = last.merge(weekly[["ubigeo", "semana_inicio", "version"]], on=["ubigeo", "semana_inicio"], how="left")
    return v.version.value_counts(dropna=False).to_dict()
