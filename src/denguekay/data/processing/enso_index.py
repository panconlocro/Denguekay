"""
Bronze (``sstoi.indices`` text) -> Silver (monthly Niño 1+2 with the date it becomes usable).

Each month carries ``fecha_disponible``: the first day it can be used at a forecast origin.
CPC updates its index files "around the 10th of each month"
(https://www.cpc.ncep.noaa.gov/data/indices/Readme.index.shtml), so month M is taken as usable
from day ``PUBLICATION_DAY`` of month M + 1. The real publication date of past months is not
recorded, so this conservative rule is applied to every month.
"""

import pandas as pd

PUBLICATION_DAY = 10
COLUMNS = ["anio", "mes", "nino12", "nino12_anom", "nino3", "nino3_anom", "nino4", "nino4_anom",
           "nino34", "nino34_anom"]


def parse_sstoi(text: str) -> pd.DataFrame:
    """Parse the whitespace table of ``sstoi.indices`` (header + one row per month)."""
    rows = [line.split() for line in text.splitlines()[1:] if line.strip()]
    if any(len(r) != len(COLUMNS) for r in rows):
        raise ValueError("Filas con un número de columnas distinto de 10 en sstoi.indices")
    data = pd.DataFrame(rows, columns=COLUMNS)
    data[["anio", "mes"]] = data[["anio", "mes"]].astype(int)
    data[COLUMNS[2:]] = data[COLUMNS[2:]].astype(float)
    if data.duplicated(["anio", "mes"]).any():
        raise ValueError("Meses duplicados en sstoi.indices")
    months = pd.PeriodIndex.from_fields(year=data.anio, month=data.mes, freq="M")
    if len(months) > 1 and not (months[1:] - months[:-1] == months.freq).all():
        raise ValueError("Meses faltantes o desordenados en sstoi.indices")
    return data


def with_availability(data: pd.DataFrame, publication_day: int = PUBLICATION_DAY) -> pd.DataFrame:
    """Add ``fecha_disponible`` = day ``publication_day`` of the month after each month."""
    out = data.copy()
    first = pd.to_datetime(dict(year=out.anio, month=out.mes, day=1))
    out["fecha_disponible"] = first + pd.DateOffset(months=1) + pd.Timedelta(days=publication_day - 1)
    return out


def nino12_monthly(text: str) -> pd.DataFrame:
    """Silver table: year, month, Niño 1+2 value and anomaly, and the date it is usable."""
    return with_availability(parse_sstoi(text))[["anio", "mes", "nino12", "nino12_anom", "fecha_disponible"]]
