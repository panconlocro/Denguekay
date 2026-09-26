"""
Descarga clima histórico diario de Open-Meteo (archive API) por distrito.

Antes el cache de parquets vivía en Drive (BASE/cache_meteo). Ahora vive
local en data/bronze/meteo/cache_meteo/, así que el "resume" (no volver a
pedir un distrito ya descargado) funciona directo contra el disco local.
"""

import time

import pandas as pd
import requests

from src.utils.paths import CACHE_METEO

URL = "https://archive-api.open-meteo.com/v1/archive"

DAILY_VARS = [
    "temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
    "precipitation_sum", "rain_sum", "relative_humidity_2m_mean",
    "wind_speed_10m_max", "shortwave_radiation_sum", "et0_fao_evapotranspiration",
]
START, END = "2017-01-01", "2025-12-31"
BATCH_SIZE = 20  # si te topa el límite antes de terminar el batch, bájalo a 15


class LimiteAPI(Exception):
    """Límite horario o diario de Open-Meteo alcanzado: no tiene sentido reintentar ahora."""


def fetch_district(lat: float, lon: float, retries: int = 4) -> pd.DataFrame:
    """Descarga el clima diario 2017-2025 para un punto (lat, lon)."""
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": START, "end_date": END,
        "daily": ",".join(DAILY_VARS),
        "timezone": "America/Lima",
    }
    for _ in range(retries):
        r = requests.get(URL, params=params, timeout=90)

        if r.status_code == 200:
            return pd.DataFrame(r.json()["daily"])

        if r.status_code == 429:
            es_json = r.headers.get("content-type", "").startswith("application/json")
            reason = r.json().get("reason", "") if es_json else r.text
            if "Hourly" in reason or "Daily" in reason:
                raise LimiteAPI(reason)  # límite horario o diario: no reintentar
            time.sleep(65)  # límite por minuto: espera y reintenta
            continue

        time.sleep(5)  # error transitorio (5xx, etc.)

    raise RuntimeError(f"Falló lat={lat}, lon={lon}: {r.status_code} {r.text[:200]}")


def _ya_descargado(id_distrito: int) -> bool:
    return (CACHE_METEO / f"distrito_{id_distrito:03d}.parquet").exists()


def descargar_batch_pendientes(distritos: pd.DataFrame, batch_size: int = BATCH_SIZE) -> int:
    """
    Descarga hasta `batch_size` distritos pendientes y los cachea en
    data/bronze/meteo/cache_meteo/distrito_XXX.parquet.

    Corre este notebook/función varias veces hasta que "Quedan: 0" —
    Open-Meteo tiene límites por minuto/hora que suelen cortar el batch.
    Devuelve cuántos distritos quedaron pendientes después de este batch.
    """
    CACHE_METEO.mkdir(parents=True, exist_ok=True)

    pendientes = distritos[~distritos["id_distrito"].apply(_ya_descargado)]
    print(f"Descargados: {len(distritos) - len(pendientes)} | Pendientes: {len(pendientes)}")

    hechos = 0
    for _, row in pendientes.head(batch_size).iterrows():
        try:
            df = fetch_district(row["lat"], row["lon"])
        except LimiteAPI as e:
            print(f"\nLímite alcanzado: {e}")
            print("Espera y vuelve a correr este bloque.")
            break

        df["id_distrito"] = row["id_distrito"]
        df.to_parquet(CACHE_METEO / f"distrito_{row['id_distrito']:03d}.parquet", index=False)
        hechos += 1
        print(f"OK {row['id_distrito']:>2} {row['distrito']}")
        time.sleep(3)

    quedan = len(pendientes) - hechos
    print(f"\nEn este batch: {hechos} | Quedan: {quedan}")
    if quedan == 0:
        print("Listo: ya se puede pasar al armado de la data diaria (bronze -> silver).")
    return quedan
