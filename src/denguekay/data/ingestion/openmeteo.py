"""
Download daily historical weather from Open-Meteo (archive API) per district.

The parquet cache used to live on Drive (BASE/cache_meteo). It now lives
locally in data/bronze/meteo/cache_meteo/, so "resume" (never requesting an
already downloaded district again) works directly against the local disk.
"""

import time

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
BATCH_SIZE = 20  # if the limit hits before the batch ends, lower it to 15


class APILimitError(Exception):
    """Open-Meteo hourly or daily limit reached: retrying now makes no sense."""


def fetch_district(
    lat: float, lon: float, retries: int = 4, *,
    start_date: str = START, end_date: str = END,
) -> pd.DataFrame:
    """Download daily weather for one point and an inclusive date range."""
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start_date, "end_date": end_date,
        "daily": ",".join(DAILY_VARS),
        "timezone": "America/Lima",
    }
    for attempt in range(retries):
        try:
            r = requests.get(URL, params=params, timeout=90)
        except requests.RequestException as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"Open-Meteo request failed for {lat}, {lon}, {start_date} to {end_date}: {exc}") from exc
            time.sleep(5)
            continue

        if r.status_code == 200:
            daily = r.json().get("daily")
            if not isinstance(daily, dict) or "time" not in daily:
                raise RuntimeError(f"Open-Meteo response missing daily data for {lat}, {lon}")
            return pd.DataFrame(daily)

        if r.status_code == 429:
            is_json = r.headers.get("content-type", "").startswith("application/json")
            reason = r.json().get("reason", "") if is_json else r.text
            if "Hourly" in reason or "Daily" in reason:
                raise APILimitError(reason)  # hourly or daily limit: do not retry
            time.sleep(65)  # per-minute limit: wait and retry
            continue

        time.sleep(5)  # transient error (5xx, etc.)

    raise RuntimeError(f"Falló lat={lat}, lon={lon}: {r.status_code} {r.text[:200]}")


def _already_downloaded(district_id: int) -> bool:
    return (CACHE_METEO / f"distrito_{district_id:03d}.parquet").exists()


def download_pending_batch(districts: pd.DataFrame, batch_size: int = BATCH_SIZE) -> int:
    """
    Download up to `batch_size` pending districts and cache them in
    data/bronze/meteo/cache_meteo/distrito_XXX.parquet.

    Run this notebook/function several times until "Quedan: 0":
    Open-Meteo has per-minute/per-hour limits that usually cut the batch.
    Returns how many districts are still pending after this batch.
    """
    CACHE_METEO.mkdir(parents=True, exist_ok=True)

    pending = districts[~districts["id_distrito"].apply(_already_downloaded)]
    print(f"Descargados: {len(districts) - len(pending)} | Pendientes: {len(pending)}")

    done = 0
    for _, row in pending.head(batch_size).iterrows():
        try:
            df = fetch_district(row["lat"], row["lon"])
        except APILimitError as e:
            print(f"\nLímite alcanzado: {e}")
            print("Espera y vuelve a correr este bloque.")
            break

        df["id_distrito"] = row["id_distrito"]
        df.to_parquet(CACHE_METEO / f"distrito_{row['id_distrito']:03d}.parquet", index=False)
        done += 1
        print(f"OK {row['id_distrito']:>2} {row['distrito']}")
        time.sleep(3)

    remaining = len(pending) - done
    print(f"\nEn este batch: {done} | Quedan: {remaining}")
    if remaining == 0:
        print("Listo: ya se puede pasar al armado de la data diaria (bronze -> silver).")
    return remaining
