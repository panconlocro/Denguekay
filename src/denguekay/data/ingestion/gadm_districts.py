"""
Download Peru's district boundaries (GADM level 3), keep Piura and compute
each district's centroid. Builds the reference catalogue
distritos_piura_coords.csv (it lives in data/reference/ and is versioned).

Requires: geopandas, requests
"""

import pandas as pd
import geopandas as gpd

from denguekay.data.keys import normalize, split_camel

GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_PER_3.json.zip"

EXPECTED_BY_PROVINCE = {
    "Piura": 10, "Ayabaca": 10, "Huancabamba": 8, "Morropón": 10,
    "Paita": 7, "Sullana": 8, "Talara": 6, "Sechura": 6,
}

# One-off fixes of official names that GADM splits wrongly or misspells
NAME_CORRECTIONS = {
    "Cura Mori": "Cura Mori",
    "El Tallan": "El Tallán",
    "La Union": "La Unión",
}

# Missing in GADM: added by hand (coordinates checked against INEI/Google Maps)
MISSING_DISTRICT = {
    "provincia": "Piura",
    "distrito": "Veintiséis de Octubre",
    "lat": -5.175,
    "lon": -80.660,
}


def download_piura_districts() -> pd.DataFrame:
    """Download GADM level 3, keep Piura and return the centroid lat/lon."""
    gdf = gpd.read_file(GADM_URL)
    piura = gdf[gdf["NAME_1"] == "Piura"].copy()

    # Metric projection (UTM 17S) so that the centroid is correct
    piura_utm = piura.to_crs(epsg=32717)
    cent = piura_utm.geometry.centroid.to_crs(epsg=4326)

    districts = pd.DataFrame({
        "provincia": piura["NAME_2"].values,
        "distrito": piura["NAME_3"].values,
        "lat": cent.y.values,
        "lon": cent.x.values,
    }).reset_index(drop=True)

    districts["id_distrito"] = districts.index + 1
    return districts


def check_count_by_province(districts: pd.DataFrame) -> None:
    """Print a quick check: number of GADM districts vs. the expected count (INEI)."""
    obtained = districts.groupby("provincia").size().to_dict()
    for prov, n in EXPECTED_BY_PROVINCE.items():
        got = obtained.get(prov, 0)
        mark = "" if got == n else "  <-- REVISAR"
        print(f"{prov:12} esperado={n:>2} GADM={got:>2}{mark}")


def clean_and_complete(districts: pd.DataFrame) -> pd.DataFrame:
    """
    Split camelCase names, apply one-off corrections, add the missing
    district and build the final distrito_key + id_distrito.
    """
    districts = districts.copy()
    districts["distrito"] = districts["distrito"].apply(split_camel)
    districts["distrito"] = districts["distrito"].replace(NAME_CORRECTIONS)

    missing = pd.DataFrame([MISSING_DISTRICT])
    districts = pd.concat(
        [districts[["provincia", "distrito", "lat", "lon"]], missing],
        ignore_index=True,
    )

    districts["distrito_key"] = districts["distrito"].apply(normalize)
    districts["id_distrito"] = districts.index + 1
    return districts


def build_district_catalog() -> pd.DataFrame:
    """Full pipeline: download -> check -> clean. Returns the final catalogue (65 districts)."""
    districts = download_piura_districts()
    check_count_by_province(districts)
    districts = clean_and_complete(districts)
    print(len(districts), "distritos")
    print(districts.groupby("provincia").size())
    return districts
