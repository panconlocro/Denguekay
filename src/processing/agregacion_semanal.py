"""
Bronze (diario, por distrito) -> Silver (semanal, todos los distritos).

Junta los parquets de data/bronze/meteo/cache_meteo/, agrega a semana
(domingo-sábado, aprox. semana epidemiológica) y cruza con el catálogo
de distritos para tener nombre/lat/lon en la salida.
"""

import pandas as pd

from src.utils.paths import CACHE_METEO
from src.utils.keys import normalizar

# Correcciones puntuales de nombres que salen mal separados/duplicados al
# cruzar meteo (via GADM) con los otros catálogos. Detectadas la primera vez
# que se hizo el merge con socio.
CORRECCIONES_NOMBRE_MERGE = {
    "Santa Catalinade Mossa": "Santa Catalina de Mossa",
    "Bellavistadela Union": "Bellavista de la Union",
    "San Juande Bigote": "San Juan de Bigote",
}

AGG_DIARIO_A_SEMANAL = {
    "temperature_2m_mean": "mean",
    "temperature_2m_max": "max",
    "temperature_2m_min": "min",
    "precipitation_sum": "sum",
    "rain_sum": "sum",
    "relative_humidity_2m_mean": "mean",
    "wind_speed_10m_max": "max",
    "shortwave_radiation_sum": "sum",
    "et0_fao_evapotranspiration": "sum",
    "time": "count",  # días con dato en la semana
}

RENOMBRE_SEMANAL = {
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

COLUMNAS_FINALES = [
    "provincia", "distrito", "lat", "lon", "anio", "semana", "semana_inicio",
    "temp_media", "temp_max", "temp_min", "precip_total_mm", "lluvia_total_mm",
    "hum_rel_media", "viento_max", "radiacion_total", "et0_total",
]


def cargar_diario_desde_cache(n_distritos_esperado: int) -> pd.DataFrame:
    """Junta todos los parquets del cache local en un solo DataFrame diario."""
    archivos = sorted(CACHE_METEO.glob("distrito_*.parquet"))
    print(len(archivos), "archivos")
    assert len(archivos) == n_distritos_esperado, (
        "Aún faltan distritos: corre descargar_batch_pendientes() de nuevo."
    )

    diario = pd.concat([pd.read_parquet(f) for f in archivos], ignore_index=True)
    diario["time"] = pd.to_datetime(diario["time"])
    return diario


def agregar_a_semanal(diario: pd.DataFrame, distritos: pd.DataFrame) -> pd.DataFrame:
    """Agrega el clima diario a semanal y le pega nombre/lat/lon de cada distrito."""
    diario = diario.copy()
    diario["semana_inicio"] = diario["time"].dt.to_period("W-SAT").dt.start_time

    semanal = (
        diario.groupby(["id_distrito", "semana_inicio"])
        .agg(AGG_DIARIO_A_SEMANAL)
        .rename(columns=RENOMBRE_SEMANAL)
        .reset_index()
    )

    # Quitar semanas parciales en los bordes (primera y última)
    semanal = semanal[semanal["n_dias"] == 7].drop(columns="n_dias")

    # Año y semana epidemiológica aproximada (jueves de la semana)
    iso = semanal["semana_inicio"] + pd.Timedelta(days=3)
    semanal["anio"] = iso.dt.isocalendar().year.values
    semanal["semana"] = iso.dt.isocalendar().week.values

    final = semanal.merge(distritos, on="id_distrito", how="left")
    final = final[COLUMNAS_FINALES].sort_values(["distrito", "semana_inicio"])
    return final


def limpiar_nombres_para_cruce(meteo: pd.DataFrame) -> pd.DataFrame:
    """
    Corrige nombres de distrito problemáticos (mal separados o duplicados
    entre provincias, ej. "Salitral" existe en Sullana y en Morropón) y
    agrega distrito_key, dejando meteo lista para cruzar con socio/epi.
    """
    meteo = meteo.copy()
    meteo["distrito"] = meteo["distrito"].replace(CORRECCIONES_NOMBRE_MERGE)

    # "Salitral" se repite en dos provincias: desambiguar la de Sullana
    meteo.loc[
        (meteo["provincia"] == "Sullana") & (meteo["distrito"] == "Salitral"),
        "distrito",
    ] = "Salitral_s"

    meteo["distrito_key"] = meteo["distrito"].apply(normalizar)
    return meteo
