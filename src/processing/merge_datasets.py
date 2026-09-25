import pandas as pd

from utils.keys import normalizar


def merge_meteo_socio(meteo: pd.DataFrame, socio_anual: pd.DataFrame):
    meteo = meteo.copy()
    meteo["distrito_key"] = meteo["distrito"].apply(normalizar)

    solo_meteo = set(meteo["distrito_key"]) - set(socio_anual["distrito_key"])
    solo_socio = set(socio_anual["distrito_key"]) - set(meteo["distrito_key"])
    if solo_meteo or solo_socio:
        raise ValueError(f"Distritos sin match. Solo en meteo: {solo_meteo} | Solo en socio: {solo_socio}")

    final = meteo.merge(
        socio_anual.drop(columns=["departamento", "provincia", "distrito"]),
        on=["distrito_key", "anio"], how="left",
    )
    assert final["poblacion"].notna().all(), "Quedaron filas sin match sociodemográfico"
    return final


def cargar_epi_piura(path_excel, anio_min, anio_max, sheet_name="Sheet1"):
    epi = pd.read_excel(path_excel, sheet_name=sheet_name)
    epi["ubigeo"] = epi["ubigeo"].astype(int)

    epi_piura = epi[
        (epi["ubigeo"] // 10000 == 20) & (epi["anio"].between(anio_min, anio_max))
    ].copy()

    epi_piura = (
        epi_piura.groupby(["ubigeo", "anio", "semana"], as_index=False)["casos_Dengue"].sum()
    )
    return epi_piura


def merge_con_epi(dataset_final: pd.DataFrame, epi_piura: pd.DataFrame):
    dataset_final = dataset_final.copy()
    dataset_final["ubigeo"] = dataset_final["ubigeo"].astype(int)

    dataset_modelo = dataset_final.merge(epi_piura, on=["ubigeo", "anio", "semana"], how="left")
    dataset_modelo["casos_Dengue"] = dataset_modelo["casos_Dengue"].fillna(0).astype(int)

    # Verificación: nada del epi debió quedarse sin match
    chk = epi_piura.merge(
        dataset_final[["ubigeo", "anio", "semana"]],
        on=["ubigeo", "anio", "semana"], how="left", indicator=True,
    )
    sin_match = chk[chk["_merge"] == "left_only"]
    if len(sin_match):
        print(f"Aviso: {len(sin_match)} filas de epi sin match — revisar definición de semana")

    return dataset_modelo