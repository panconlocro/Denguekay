import geopandas as gpd
import pandas as pd

from utils.keys import separar_camel, normalizar

GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_PER_3.json.zip"

# GADM no trae "Veintiséis de Octubre" por separado (queda fusionado con Piura).
# Coordenadas aproximadas — reemplázalas por el centroide real (INEI) cuando lo tengas.
DISTRITO_FALTANTE = {
    "provincia": "Piura",
    "distrito": "Veintiséis de Octubre",
    "lat": -5.175,
    "lon": -80.660,
}

NOMBRES_CORRECCION = {
    "El Tallan": "El Tallán",
    "La Union": "La Unión",
}


def obtener_distritos_piura():
    gdf = gpd.read_file(GADM_URL)
    piura = gdf[gdf["NAME_1"] == "Piura"].copy()

    piura_utm = piura.to_crs(epsg=32717)
    cent = piura_utm.geometry.centroid.to_crs(epsg=4326)

    distritos = pd.DataFrame({
        "provincia": piura["NAME_2"].values,
        "distrito": piura["NAME_3"].values,
        "lat": cent.y.values,
        "lon": cent.x.values,
    })

    distritos["distrito"] = distritos["distrito"].apply(separar_camel)
    distritos["distrito"] = distritos["distrito"].replace(NOMBRES_CORRECCION)

    distritos = pd.concat(
        [distritos, pd.DataFrame([DISTRITO_FALTANTE])], ignore_index=True
    )

    distritos["distrito_key"] = distritos["distrito"].apply(normalizar)
    distritos["id_distrito"] = distritos.index + 1

    assert len(distritos) == 65, f"Se esperaban 65 distritos, salieron {len(distritos)}"
    return distritos