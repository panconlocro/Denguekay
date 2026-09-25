import time
import requests
import pandas as pd

URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY_VARS = [
    "temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
    "precipitation_sum", "rain_sum", "relative_humidity_2m_mean",
    "wind_speed_10m_max", "shortwave_radiation_sum", "et0_fao_evapotranspiration",
]


class LimiteAPI(Exception):
    """Se levanta cuando Open-Meteo devuelve un límite horario/diario (no tiene caso reintentar)."""
    pass


def fetch_district(lat, lon, start_date, end_date, retries=4):
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start_date, "end_date": end_date,
        "daily": ",".join(DAILY_VARS),
        "timezone": "America/Lima",
    }
    for _ in range(retries):
        r = requests.get(URL, params=params, timeout=90)
        if r.status_code == 200:
            return pd.DataFrame(r.json()["daily"])
        if r.status_code == 429:
            reason = r.json().get("reason", "") if "application/json" in r.headers.get("content-type", "") else r.text
            if "Hourly" in reason or "Daily" in reason:
                raise LimiteAPI(reason)
            time.sleep(65)
            continue
        time.sleep(5)
    raise RuntimeError(f"Falló lat={lat}, lon={lon}: {r.status_code} {r.text[:200]}")


def ya_descargado(id_distrito, cache_dir):
    return (cache_dir / f"distrito_{id_distrito:03d}.parquet").exists()


def descargar_batch(distritos, cache_dir, batch_size, start_date, end_date, pausa=3):
    """Descarga hasta batch_size distritos pendientes. Devuelve (n_hechos, motivo_limite_o_None)."""
    pendientes = distritos[~distritos["id_distrito"].apply(lambda i: ya_descargado(i, cache_dir))]
    hechos = 0
    for _, row in pendientes.head(batch_size).iterrows():
        try:
            df = fetch_district(row["lat"], row["lon"], start_date, end_date)
        except LimiteAPI as e:
            return hechos, str(e)
        df["id_distrito"] = row["id_distrito"]
        df.to_parquet(cache_dir / f"distrito_{row['id_distrito']:03d}.parquet", index=False)
        hechos += 1
        time.sleep(pausa)
    return hechos, None