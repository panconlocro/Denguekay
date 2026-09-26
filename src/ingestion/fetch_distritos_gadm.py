"""
Descarga los límites distritales de Perú (GADM nivel 3), filtra Piura y
calcula el centroide de cada distrito. Genera el catálogo de referencia
distritos_piura_coords.csv (va en data/reference/, sí se sube a Git).

Requiere: geopandas, requests
"""

import pandas as pd
import geopandas as gpd

from src.utils.keys import normalizar, separar_camel

GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_PER_3.json.zip"

ESPERADO_POR_PROVINCIA = {
    "Piura": 10, "Ayabaca": 10, "Huancabamba": 8, "Morropón": 10,
    "Paita": 7, "Sullana": 8, "Talara": 6, "Sechura": 6,
}

# Ajustes puntuales de nombres oficiales que GADM entrega mal separados/con typo
CORRECCIONES_NOMBRE = {
    "Cura Mori": "Cura Mori",
    "El Tallan": "El Tallán",
    "La Union": "La Unión",
}

# Falta en GADM: se agrega manualmente (coordenadas verificadas con INEI/Google Maps)
DISTRITO_FALTANTE = {
    "provincia": "Piura",
    "distrito": "Veintiséis de Octubre",
    "lat": -5.175,
    "lon": -80.660,
}


def descargar_distritos_piura() -> pd.DataFrame:
    """Descarga GADM nivel 3, filtra Piura y devuelve lat/lon de centroides."""
    gdf = gpd.read_file(GADM_URL)
    piura = gdf[gdf["NAME_1"] == "Piura"].copy()

    # Proyección métrica (UTM 17S) para que el centroide sea correcto
    piura_utm = piura.to_crs(epsg=32717)
    cent = piura_utm.geometry.centroid.to_crs(epsg=4326)

    distritos = pd.DataFrame({
        "provincia": piura["NAME_2"].values,
        "distrito": piura["NAME_3"].values,
        "lat": cent.y.values,
        "lon": cent.x.values,
    }).reset_index(drop=True)

    distritos["id_distrito"] = distritos.index + 1
    return distritos


def validar_conteo_por_provincia(distritos: pd.DataFrame) -> None:
    """Imprime un chequeo rápido: cantidad de distritos GADM vs. lo esperado (INEI)."""
    obtenido = distritos.groupby("provincia").size().to_dict()
    for prov, n in ESPERADO_POR_PROVINCIA.items():
        got = obtenido.get(prov, 0)
        marca = "" if got == n else "  <-- REVISAR"
        print(f"{prov:12} esperado={n:>2} GADM={got:>2}{marca}")


def limpiar_y_completar(distritos: pd.DataFrame) -> pd.DataFrame:
    """
    Separa nombres camelCase, aplica correcciones puntuales, agrega el
    distrito faltante y genera distrito_key + id_distrito definitivos.
    """
    distritos = distritos.copy()
    distritos["distrito"] = distritos["distrito"].apply(separar_camel)
    distritos["distrito"] = distritos["distrito"].replace(CORRECCIONES_NOMBRE)

    faltante = pd.DataFrame([DISTRITO_FALTANTE])
    distritos = pd.concat(
        [distritos[["provincia", "distrito", "lat", "lon"]], faltante],
        ignore_index=True,
    )

    distritos["distrito_key"] = distritos["distrito"].apply(normalizar)
    distritos["id_distrito"] = distritos.index + 1
    return distritos


def construir_catalogo_distritos() -> pd.DataFrame:
    """Pipeline completo: descarga -> valida -> limpia. Devuelve el catálogo final (65 distritos)."""
    distritos = descargar_distritos_piura()
    validar_conteo_por_provincia(distritos)
    distritos = limpiar_y_completar(distritos)
    print(len(distritos), "distritos")
    print(distritos.groupby("provincia").size())
    return distritos
