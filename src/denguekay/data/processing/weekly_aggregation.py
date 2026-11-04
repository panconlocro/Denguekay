"""
Bronze (daily, per district) -> Silver (weekly, every district).

Gathers the parquets of data/bronze/meteo/cache_meteo/, aggregates them to
weeks (Sunday-Saturday, MMWR calendar) and joins the district catalogue to
have name/lat/lon in the output.
"""

from pathlib import Path

import pandas as pd

from denguekay.config.paths import CACHE_METEO
from denguekay.data.keys import normalize
from denguekay.data.calendar import mmwr_epi_week

# One-off fixes of names that come out wrongly split/duplicated when
# joining meteo (via GADM) with the other catalogues. Found the first time
# the merge with socio was done.
MERGE_NAME_CORRECTIONS = {
    "Santa Catalinade Mossa": "Santa Catalina de Mossa",
    "Bellavistadela Union": "Bellavista de la Union",
    "San Juande Bigote": "San Juan de Bigote",
}

DAILY_TO_WEEKLY_AGG = {
    "temperature_2m_mean": "mean",
    "temperature_2m_max": "max",
    "temperature_2m_min": "min",
    "precipitation_sum": "sum",
    "rain_sum": "sum",
    "relative_humidity_2m_mean": "mean",
    "wind_speed_10m_max": "max",
    "shortwave_radiation_sum": "sum",
    "et0_fao_evapotranspiration": "sum",
    "time": "count",  # days with data in the week
}

WEEKLY_RENAME = {
    "temperature_2m_mean": "temp_media",
    "temperature_2m_max": "temp_max",
    "temperature_2m_min": "temp_min",
    "precipitation_sum": "precip_total_mm",
    "rain_sum": "lluvia_total_mm",
    "relative_humidity_2m_mean": "hum_rel_media",
    "wind_speed_10m_max": "viento_max",
    "shortwave_radiation_sum": "radiacion_total",
    "et0_fao_evapotranspiration": "et0_total",
    "time": "n_dias",
}

FINAL_COLUMNS = [
    "provincia", "distrito", "lat", "lon", "anio", "semana", "semana_inicio",
    "temp_media", "temp_max", "temp_min", "precip_total_mm", "lluvia_total_mm",
    "hum_rel_media", "viento_max", "radiacion_total", "et0_total",
]


def load_daily_from_cache(expected_districts: int, cache_dir: Path = CACHE_METEO) -> pd.DataFrame:
    """Gather every parquet of a local cache (default cache_meteo/) into a single daily DataFrame."""
    files = sorted(cache_dir.glob("distrito_*.parquet"))
    print(len(files), "archivos")
    assert len(files) == expected_districts, (
        "Aún faltan distritos: corre descargar_batch_pendientes() de nuevo."
    )

    daily = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    daily["time"] = pd.to_datetime(daily["time"])
    return daily


def aggregate_to_weekly(
    daily: pd.DataFrame, districts: pd.DataFrame, *, include_id: bool = False,
) -> pd.DataFrame:
    """Aggregate daily weather to weekly and attach each district's name/lat/lon."""
    daily = daily.copy()
    daily["time"] = pd.to_datetime(daily["time"])
    daily["semana_inicio"] = daily["time"].dt.to_period("W-SAT").dt.start_time

    weekly = (
        daily.groupby(["id_distrito", "semana_inicio"])
        .agg(DAILY_TO_WEEKLY_AGG)
        .rename(columns=WEEKLY_RENAME)
        .reset_index()
    )

    # Drop partial weeks at the edges (first and last)
    weekly = weekly[weekly["n_dias"] == 7].drop(columns="n_dias")

    # MMWR numbering keeps 2025-S53 and starts 2026-S01 on 4 January.
    calendar = mmwr_epi_week(weekly["semana_inicio"])
    weekly["anio"] = calendar["anio_epi"].to_numpy()
    weekly["semana"] = calendar["semana_epi"].to_numpy()

    final = weekly.merge(districts, on="id_distrito", how="left")
    columns = (["id_distrito"] if include_id else []) + FINAL_COLUMNS
    final = final[columns].sort_values(["distrito", "semana_inicio"])
    return final


def clean_names_for_join(meteo: pd.DataFrame) -> pd.DataFrame:
    """
    Fix problematic district names (wrongly split or duplicated across
    provinces, e.g. "Salitral" exists in Sullana and in Morropon) and
    add distrito_key, leaving meteo ready to join with socio/epi.
    """
    meteo = meteo.copy()
    meteo["distrito"] = meteo["distrito"].replace(MERGE_NAME_CORRECTIONS)

    # "Salitral" repeats in two provinces: disambiguate the one in Sullana
    meteo.loc[
        (meteo["provincia"] == "Sullana") & (meteo["distrito"] == "Salitral"),
        "distrito",
    ] = "Salitral_s"

    meteo["distrito_key"] = meteo["distrito"].apply(normalize)
    return meteo


def load_daily_from_caches(cache_dirs: list[Path], expected_districts: int) -> pd.DataFrame:
    """Daily weather of several caches of the same model (e.g. 2000-2016 and 2017-2025), one frame.

    Every cache must hold `expected_districts` districts, and a district-day may appear in only one
    cache (the ranges must not overlap).
    """
    daily = pd.concat([load_daily_from_cache(expected_districts, cache_dir=c) for c in cache_dirs],
                      ignore_index=True)
    if daily.duplicated(["id_distrito", "time"]).any():
        raise ValueError("Los cachés se solapan: hay distrito-días repetidos.")
    return daily


def aggregate_available_to_weekly(daily: pd.DataFrame, districts: pd.DataFrame, variables: list[str]) -> pd.DataFrame:
    """Weekly aggregation of only `variables` (daily names), leaving a week with no data empty, not 0.

    Same weeks, calendar and edge rule as `aggregate_to_weekly` (only weeks with 7 days). The sums
    use ``min_count=1``: a variable the model does not provide stays NaN instead of turning into 0.
    Output: id_distrito, provincia, distrito, lat, lon, anio, semana, semana_inicio + the renamed variables.
    """
    missing = [v for v in variables if v not in DAILY_TO_WEEKLY_AGG or v == "time"]
    if missing:
        raise ValueError(f"Variables sin regla de agregación: {missing}")
    daily = daily.copy()
    daily["time"] = pd.to_datetime(daily["time"])
    daily["semana_inicio"] = daily["time"].dt.to_period("W-SAT").dt.start_time
    groups = daily.groupby(["id_distrito", "semana_inicio"])
    parts = {"n_dias": groups["time"].count()}
    for v in variables:
        how = DAILY_TO_WEEKLY_AGG[v]
        parts[WEEKLY_RENAME[v]] = groups[v].sum(min_count=1) if how == "sum" else groups[v].agg(how)
    weekly = pd.DataFrame(parts).reset_index()
    weekly = weekly[weekly["n_dias"] == 7].drop(columns="n_dias")
    calendar = mmwr_epi_week(weekly["semana_inicio"])
    weekly["anio"] = calendar["anio_epi"].to_numpy()
    weekly["semana"] = calendar["semana_epi"].to_numpy()
    final = weekly.merge(districts[["id_distrito", "provincia", "distrito", "lat", "lon"]], on="id_distrito", how="left")
    columns = ["id_distrito", "provincia", "distrito", "lat", "lon", "anio", "semana", "semana_inicio",
               *(WEEKLY_RENAME[v] for v in variables)]
    return final[columns].sort_values(["distrito", "semana_inicio"]).reset_index(drop=True)
