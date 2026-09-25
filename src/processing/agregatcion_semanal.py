from pathlib import Path
import pandas as pd

from utils.keys import semana_epi

AGG = {
    "temperature_2m_mean": "mean", "temperature_2m_max": "max", "temperature_2m_min": "min",
    "precipitation_sum": "sum", "rain_sum": "sum", "relative_humidity_2m_mean": "mean",
    "wind_speed_10m_max": "max", "shortwave_radiation_sum": "sum",
    "et0_fao_evapotranspiration": "sum", "time": "count",
}
RENOMBRE = {
    "temperature_2m_mean": "temp_media", "temperature_2m_max": "temp_max",
    "temperature_2m_min": "temp_min", "precipitation_sum": "precip_total_mm",
    "rain_sum": "lluvia_total_mm", "relative_humidity_2m_mean": "hum_rel_media",
    "wind_speed_10m_max": "viento_max", "shortwave_radiation_sum": "radiacion_total",
    "et0_fao_evapotranspiration": "et0_total", "time": "n_dias",
}


def unir_parquets_diarios(cache_dir: Path):
    archivos = sorted(cache_dir.glob("distrito_*.parquet"))
    diario = pd.concat([pd.read_parquet(f) for f in archivos], ignore_index=True)
    diario["time"] = pd.to_datetime(diario["time"])
    return diario


def agregar_semanal(diario: pd.DataFrame, distritos: pd.DataFrame):
    diario = diario.copy()
    diario["semana_inicio"] = diario["time"].dt.to_period("W-SAT").dt.start_time

    semanal = (
        diario.groupby(["id_distrito", "semana_inicio"]).agg(AGG)
        .rename(columns=RENOMBRE).reset_index()
    )
    semanal = semanal[semanal["n_dias"] == 7].drop(columns="n_dias")

    res = semanal["semana_inicio"].apply(semana_epi)
    semanal["anio"] = res.apply(lambda x: x[0])
    semanal["semana"] = res.apply(lambda x: x[1])

    final = semanal.merge(distritos, on="id_distrito", how="left")
    cols = ["provincia", "distrito", "distrito_key", "ubigeo", "lat", "lon",
            "anio", "semana", "semana_inicio",
            "temp_media", "temp_max", "temp_min", "precip_total_mm", "lluvia_total_mm",
            "hum_rel_media", "viento_max", "radiacion_total", "et0_total"]
    # ubigeo aún no existe en distritos (viene del Excel socio) — se agrega después del merge con socio
    cols = [c for c in cols if c in final.columns]
    return final[cols].sort_values(["distrito", "semana_inicio"])