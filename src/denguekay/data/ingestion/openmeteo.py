"""
Download daily historical weather from Open-Meteo (archive API) per district.

The parquet cache used to live on Drive (BASE/cache_meteo). It now lives
locally in data/bronze/meteo/cache_meteo/, so "resume" (never requesting an
already downloaded district again) works directly against the local disk.
"""

import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from denguekay.config.paths import CACHE_METEO

URL = "https://archive-api.open-meteo.com/v1/archive"

DAILY_VARS = [
    "temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
    "precipitation_sum", "rain_sum", "relative_humidity_2m_mean",
    "wind_speed_10m_max", "shortwave_radiation_sum", "et0_fao_evapotranspiration",
]
START, END = "2017-01-01", "2025-12-31"
GRID_COLUMNS = {"lat_celda": "latitude", "lon_celda": "longitude", "elevacion_celda": "elevation"}
BATCH_SIZE = 20  # if the limit hits before the batch ends, lower it to 15
HOURLY_WAIT_SECONDS = 61 * 60   # download_all: wait after the hourly limit (one hour plus a margin)
MAX_HOURLY_WAITS = 24


class APILimitError(Exception):
    """Open-Meteo hourly or daily limit reached: retrying now makes no sense.

    ``kind`` is "hourly" or "daily", read from the API's reason.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.kind = "daily" if "Daily" in reason else "hourly"


def fetch_district(
    lat: float, lon: float, retries: int = 4, *,
    start_date: str = START, end_date: str = END, models: str | None = None,
) -> pd.DataFrame:
    """
    Download daily weather for one point and an inclusive date range.

    `models=None` sends no `models` parameter (the API picks its default
    "Best match", as in the 2017-2025 download). A string fixes one model and
    the response must then carry exactly DAILY_VARS.
    """
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start_date, "end_date": end_date,
        "daily": ",".join(DAILY_VARS),
        "timezone": "America/Lima",
    }
    if models is not None:
        params["models"] = models
    for attempt in range(retries):
        try:
            r = requests.get(URL, params=params, timeout=90)
        except requests.RequestException as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"Open-Meteo request failed for {lat}, {lon}, {start_date} to {end_date}: {exc}") from exc
            time.sleep(5)
            continue

        if r.status_code == 200:
            body = r.json()
            daily = body.get("daily")
            if not isinstance(daily, dict) or "time" not in daily:
                raise RuntimeError(f"Open-Meteo response missing daily data for {lat}, {lon}")
            if models is None:
                return pd.DataFrame(daily)
            if sorted(daily) != sorted(["time", *DAILY_VARS]):
                raise RuntimeError(f"Open-Meteo returned unexpected columns for models={models}: {sorted(daily)}")
            # With a fixed model, keep the grid cell the API used (to see which districts share one).
            return pd.DataFrame(daily).assign(**{name: body.get(key) for name, key in GRID_COLUMNS.items()})

        if r.status_code == 429:
            is_json = r.headers.get("content-type", "").startswith("application/json")
            reason = r.json().get("reason", "") if is_json else r.text
            if "Hourly" in reason or "Daily" in reason:
                raise APILimitError(reason)  # hourly or daily limit: do not retry
            time.sleep(65)  # per-minute limit: wait and retry
            continue

        time.sleep(5)  # transient error (5xx, etc.)

    raise RuntimeError(f"Falló lat={lat}, lon={lon}: {r.status_code} {r.text[:200]}")


def _already_downloaded(district_id: int, cache_dir: Path = CACHE_METEO) -> bool:
    return (cache_dir / f"distrito_{district_id:03d}.parquet").exists()


def download_pending_batch(
    districts: pd.DataFrame, batch_size: int = BATCH_SIZE, *,
    start_date: str = START, end_date: str = END, models: str | None = None,
    cache_dir: Path = CACHE_METEO, raise_on_limit: bool = False,
) -> int:
    """
    Download up to `batch_size` pending districts and cache them in
    `cache_dir`/distrito_XXX.parquet (default data/bronze/meteo/cache_meteo/).

    Run this notebook/function several times until "Quedan: 0":
    Open-Meteo has per-minute/per-hour limits that usually cut the batch.
    Returns how many districts are still pending after this batch.

    Another date range or a fixed model must go to its own `cache_dir`:
    "resume" only checks that the district's file exists. With `raise_on_limit`
    the hourly or daily limit is raised (APILimitError) instead of printed; the
    districts already downloaded stay in the cache.
    """
    if cache_dir == CACHE_METEO and (start_date, end_date, models) != (START, END, None):
        raise ValueError("Otro rango o modelo necesita su propio cache_dir: no se mezcla con cache_meteo/.")
    cache_dir.mkdir(parents=True, exist_ok=True)

    pending = districts[~districts["id_distrito"].apply(_already_downloaded, cache_dir=cache_dir)]
    print(f"Descargados: {len(districts) - len(pending)} | Pendientes: {len(pending)}")

    done = 0
    for _, row in pending.head(batch_size).iterrows():
        try:
            df = fetch_district(row["lat"], row["lon"], start_date=start_date, end_date=end_date, models=models)
        except APILimitError as e:
            if raise_on_limit:
                raise
            print(f"\nLímite alcanzado: {e}")
            print("Espera y vuelve a correr este bloque.")
            break

        df["id_distrito"] = row["id_distrito"]
        df.to_parquet(cache_dir / f"distrito_{row['id_distrito']:03d}.parquet", index=False)
        done += 1
        print(f"OK {row['id_distrito']:>2} {row['distrito']}")
        time.sleep(3)

    remaining = len(pending) - done
    print(f"\nEn este batch: {done} | Quedan: {remaining}")
    if remaining == 0:
        print("Listo: ya se puede pasar al armado de la data diaria (bronze -> silver).")
    return remaining


def download_all(
    districts: pd.DataFrame, *, hourly_wait: float = HOURLY_WAIT_SECONDS, max_hourly_waits: int = MAX_HOURLY_WAITS,
    sleep=time.sleep, **kwargs,
) -> int:
    """
    Download every pending district of `districts`, waiting on its own after the hourly limit.

    Same arguments as `download_pending_batch` (`models`, `cache_dir`, dates). After the
    hourly limit it prints the time it will resume, waits `hourly_wait` seconds and goes on;
    it stops after the daily limit or after `max_hourly_waits` waits. Returns how many
    districts are still pending (0 = done). Running it again resumes from the cache.
    """
    waits = 0
    while True:
        try:
            return download_pending_batch(districts, batch_size=len(districts), raise_on_limit=True, **kwargs)
        except APILimitError as e:
            cache_dir = kwargs.get("cache_dir", CACHE_METEO)
            remaining = int((~districts["id_distrito"].apply(_already_downloaded, cache_dir=cache_dir)).sum())
            if e.kind == "daily":
                print(f"\nLímite diario: {e}\nSe detiene con {remaining} pendientes; vuelve a correr la celda mañana.")
                return remaining
            if waits >= max_hourly_waits:
                print(f"\nSe alcanzaron {max_hourly_waits} esperas; quedan {remaining}. Vuelve a correr la celda.")
                return remaining
            waits += 1
            resume = datetime.now() + timedelta(seconds=hourly_wait)
            print(f"\nLímite por hora ({remaining} pendientes). Espera {waits}: reanuda a las {resume:%H:%M}.")
            sleep(hourly_wait)
