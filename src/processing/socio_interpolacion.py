"""
Bronze (Excel sociodemográfico, 1 fila por distrito con columnas _2017/_2025)
-> Silver (socio_anual.csv: 1 fila por distrito x año, 2017-2025).

Variables con dato en 2017 y 2025 se interpolan linealmente año a año.
Variables con un solo año disponible (ej. fraccion_menores_5 solo 2017,
fraccion_60_mas solo 2025) se descartan del dataset final: no hay forma
de interpolarlas ni de asumir que se mantuvieron constantes 8 años, así
que se excluyen en vez de rellenarlas con un supuesto poco confiable.
Decisión tomada — cierra el pendiente que estaba en docs/estructuraRepo.md,
sección 8.
"""

import re
import logging
from pathlib import Path

import pandas as pd

from src.utils.keys import normalizar

ANIOS = list(range(2017, 2026))
SOCIO_COLUMNS = [
    "poblacion", "fraccion_rural", "fraccion_mujeres", "fraccion_menores_15",
    "fraccion_sin_seguro", "fraccion_analfabeta_15_mas", "fraccion_pared_precaria",
    "fraccion_piso_tierra", "fraccion_agua_red", "fraccion_agua_cisterna",
    "fraccion_desague_red", "fraccion_sin_saneamiento", "fraccion_alumbrado_red",
    "fraccion_hogares_refrigeradora", "fraccion_hogares_celular",
    "fraccion_hogares_lena",
]

# Distrito con nombre repetido en el Excel original (ver limpiar_duplicados)
FIX_DISTRITO_DUPLICADO = {52: "SALITRAL_S"}


def cargar_crudo(path_excel) -> pd.DataFrame:
    return pd.read_excel(path_excel)


def limpiar_duplicados(df_pob: pd.DataFrame) -> pd.DataFrame:
    """
    Quita columnas "_consulta" duplicadas y corrige el distrito que
    aparece dos veces con el mismo nombre (mismo criterio que en meteo:
    un sufijo _S para desambiguar).
    """
    df_pob = df_pob.copy()
    df_pob["distrito_key"] = df_pob["distrito"].apply(normalizar)
    df_pob = df_pob.drop(columns=["pob_censada_2025_consulta", "fraccion_mujeres_2025_consulta"])

    for idx, nuevo_nombre in FIX_DISTRITO_DUPLICADO.items():
        if idx in df_pob.index:
            df_pob.loc[idx, "distrito"] = nuevo_nombre

    df_pob["distrito_key"] = df_pob["distrito"].apply(normalizar)

    assert df_pob["distrito_key"].is_unique, "Hay distritos duplicados en el Excel"
    assert df_pob["ubigeo"].is_unique
    return df_pob


def _construir_poblacion_larga(df_pob: pd.DataFrame, id_cols: list[str]) -> pd.DataFrame:
    """Población: 2017 = censo, 2018-2025 = proyectada. Devuelve formato largo (1 fila por año)."""
    poblacion = df_pob[id_cols].copy()
    poblacion["pob_2017"] = df_pob["pob_censada_2017"]
    for a in range(2018, 2026):
        poblacion[f"pob_{a}"] = df_pob[f"pob_proyectada_{a}"]

    pob_long = poblacion.melt(
        id_vars=id_cols, value_vars=[f"pob_{a}" for a in ANIOS],
        var_name="anio", value_name="poblacion",
    )
    pob_long["anio"] = pob_long["anio"].str.replace("pob_", "").astype(int)
    return pob_long


def construir_socio_anual(df_pob: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte el Excel sociodemográfico (ancho, 1 fila x distrito) a formato
    largo (1 fila x distrito x año), interpolando linealmente las variables
    que tienen valor en 2017 y 2025.
    """
    pob_cols = [c for c in df_pob.columns if c.startswith("pob_")]
    id_cols = ["ubigeo", "departamento", "provincia", "distrito", "distrito_key"]
    resto_cols = [c for c in df_pob.columns if c not in pob_cols + id_cols]

    pob_long = _construir_poblacion_larga(df_pob, id_cols)

    # Detectar variables base y en qué años existen (columnas tipo "<base>_2017" / "<base>_2025")
    patron = re.compile(r"^(.*)_(2017|2025)$")
    pares: dict[str, dict[int, str]] = {}
    for c in resto_cols:
        m = patron.match(c)
        if not m:
            continue
        base, anio = m.group(1), int(m.group(2))
        pares.setdefault(base, {})[anio] = c

    solo_un_anio = {b: list(d.keys()) for b, d in pares.items() if len(d) == 1}
    if solo_un_anio:
        print("Variables con un solo año disponible (se descartan, no se interpolan):")
        for b, anios in solo_un_anio.items():
            print(f"  - {b} (solo {anios[0]})")

    pares_interpolables = {b: d for b, d in pares.items() if len(d) == 2}

    frames = [pob_long.set_index(id_cols + ["anio"])]

    for base, d in pares_interpolables.items():
        tabla = pd.DataFrame(index=df_pob.index)
        v17 = df_pob[d[2017]].values
        v25 = df_pob[d[2025]].values
        for a in ANIOS:
            frac = (a - 2017) / (2025 - 2017)
            tabla[a] = v17 + (v25 - v17) * frac

        tabla[id_cols] = df_pob[id_cols]
        tabla_long = tabla.melt(
            id_vars=id_cols, value_vars=ANIOS, var_name="anio", value_name=base,
        )
        tabla_long["anio"] = tabla_long["anio"].astype(int)
        frames.append(tabla_long.set_index(id_cols + ["anio"]))

    socio_anual = pd.concat(frames, axis=1).reset_index()
    print(socio_anual.shape)  # esperado: 65 distritos x 9 años = 585 filas
    return socio_anual


def generar_socio_para_claves(
    keys: set[tuple[str, int]], silver_path: Path, bronze_path: Path,
    *, prefer_bronze: bool = False,
) -> pd.DataFrame:
    """Return only requested UBIGEO-years; extrapolate beyond 2025 if needed."""
    if not keys:
        return pd.DataFrame(columns=["ubigeo", "anio", *SOCIO_COLUMNS])
    if prefer_bronze:
        if not bronze_path.exists():
            raise FileNotFoundError(f"Required raw demographic source is unavailable: {bronze_path}")
        source = construir_socio_anual(limpiar_duplicados(cargar_crudo(bronze_path)))
    elif silver_path.exists():
        source = pd.read_csv(silver_path, dtype={"ubigeo": "string"})
    elif bronze_path.exists():
        source = construir_socio_anual(limpiar_duplicados(cargar_crudo(bronze_path)))
    else:
        raise FileNotFoundError(f"Required demographic source is unavailable: {silver_path} or {bronze_path}")
    missing_columns = set(["ubigeo", "anio", *SOCIO_COLUMNS]) - set(source)
    if missing_columns:
        raise ValueError(f"Demographic source lacks columns: {sorted(missing_columns)}")
    source = source.copy()
    source["ubigeo"] = source["ubigeo"].astype("string").str.zfill(6)
    source["anio"] = source["anio"].astype(int)
    if source.duplicated(["ubigeo", "anio"]).any():
        raise ValueError("Demographic source contains duplicate UBIGEO-years")
    indexed = source.set_index(["ubigeo", "anio"])
    result = []
    for ubigeo, year in sorted(keys):
        if year <= 2025:
            if (ubigeo, year) not in indexed.index:
                raise ValueError(f"Demographic source has no district-year: {ubigeo}, {year}")
            values = indexed.loc[(ubigeo, year), SOCIO_COLUMNS].to_dict()
        else:
            if (ubigeo, 2017) not in indexed.index or (ubigeo, 2025) not in indexed.index:
                raise ValueError(f"Demographic endpoints missing for {ubigeo}")
            first = indexed.loc[(ubigeo, 2017), SOCIO_COLUMNS]
            last = indexed.loc[(ubigeo, 2025), SOCIO_COLUMNS]
            values = {}
            for column in SOCIO_COLUMNS:
                estimate = float(last[column]) + (year - 2025) * (float(last[column]) - float(first[column])) / 8
                if column.startswith("fraccion_"):
                    capped = min(1.0, max(0.0, estimate))
                    if capped != estimate:
                        logging.info(
                            "Clamped demographic value: district=%s period=%s variable=%s original=%s final=%s",
                            ubigeo, year, column, estimate, capped,
                        )
                    values[column] = capped
                else:
                    values[column] = int(round(estimate))
                    if values[column] <= 0:
                        raise ValueError(f"Projected population is nonpositive: {ubigeo}, {year}")
        if any(pd.isna(values[column]) for column in SOCIO_COLUMNS):
            raise ValueError(f"Demographic source has missing values: {ubigeo}, {year}")
        result.append({"ubigeo": ubigeo, "anio": year, **values})
    return pd.DataFrame(result)
