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

import pandas as pd

from src.utils.keys import normalizar

ANIOS = list(range(2017, 2026))

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
