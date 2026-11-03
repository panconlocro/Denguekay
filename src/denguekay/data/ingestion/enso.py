"""
Download the coastal El Niño index: Niño 1+2 sea surface temperature from NOAA CPC.

Source: https://www.cpc.ncep.noaa.gov/data/indices/sstoi.indices (monthly OISST v2.1,
1991-2020 base, from 1982-01; Niño 1+2 = 0-10S, 90W-80W). NWS/CPC information is in the
public domain (https://www.weather.gov/disclaimer). The raw text is kept in bronze, one
file per download date, never overwritten.
"""

import datetime as dt
from pathlib import Path

import requests

from denguekay.config.paths import BRONZE_ENSO

URL_SSTOI = "https://www.cpc.ncep.noaa.gov/data/indices/sstoi.indices"
HEADER = "YR MON  NINO1+2   ANOM   NINO3    ANOM   NINO4    ANOM NINO3.4    ANOM"


def download_sstoi(target_dir: Path = BRONZE_ENSO, today: dt.date | None = None) -> Path:
    """Save the current ``sstoi.indices`` as ``sstoi_<YYYYMMDD>.indices`` (refuses to overwrite)."""
    today = today or dt.date.today()
    path = target_dir / f"sstoi_{today:%Y%m%d}.indices"
    if path.exists():
        raise FileExistsError(f"Ya existe {path.name}: bronze no se sobrescribe.")
    r = requests.get(URL_SSTOI, timeout=60)
    r.raise_for_status()
    if HEADER.split() != r.text.splitlines()[0].split():
        raise RuntimeError(f"Encabezado inesperado en sstoi.indices: {r.text.splitlines()[0]!r}")
    target_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(r.text, encoding="utf-8")
    return path
