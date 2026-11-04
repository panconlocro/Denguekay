"""
Bronze CHIRPS v3 (daily Piura windows) -> weekly precipitation per district, with its availability date.

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
