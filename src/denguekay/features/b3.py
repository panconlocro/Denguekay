"""Availability-aware climate inputs of the frozen B3 model at a single origin."""

import numpy as np
import pandas as pd

WEATHER = {
    "hum_rel_media": ("fecha_era5_land_disponible", "hum_rel_media_media5_h2_obs"),
    "precip_total_mm": ("fecha_chirps_disponible", "precip_total_mm_media5_h2_obs"),
    "temp_media": ("fecha_era5_land_disponible", "temp_media_media5_h2_obs"),
}
NINO = "nino12_anom_media3_obs"
GEO = ("lat", "lon", "elevacion_dem90")


def climate_vector(weekly, enso, end, districts):
    """Use exactly weeks o−6…o−2 and the last three available consecutive Niño months."""
    cutoff = pd.Timestamp(end)
    weeks = pd.date_range(end=cutoff - pd.Timedelta(days=20), periods=5, freq="W-SUN")
    key = pd.MultiIndex.from_product([districts, weeks], names=["ubigeo", "semana_inicio"])
    data = weekly.set_index(key.names).reindex(key)
    out = pd.DataFrame(index=districts)
    for value, (available, name) in WEATHER.items():
        known = data[value].where(data[available].le(cutoff))
        by_district = known.groupby(level="ubigeo")
        out[name] = (by_district.sum(min_count=5) / 5).reindex(districts)

    eligible = enso.loc[pd.to_datetime(enso.fecha_disponible).le(cutoff)].sort_values("mes").tail(3)
    months = pd.PeriodIndex(pd.to_datetime(eligible.mes), freq="M")
    consecutive = len(months) == 3 and (np.diff(months.asi8) == 1).all()
    out[NINO] = eligible.nino12_anom.mean() if consecutive and eligible.nino12_anom.notna().all() else np.nan
    return out
