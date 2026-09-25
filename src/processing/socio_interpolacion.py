import re
import pandas as pd

from utils.keys import normalizar

ANIOS = list(range(2017, 2026))
COLUMNAS_DUPLICADAS = ["pob_censada_2025_consulta", "fraccion_mujeres_2025_consulta"]


def cargar_socio(path_excel, sheet_name="Hoja 2"):
    socio = pd.read_excel(path_excel, sheet_name=sheet_name)
    socio["distrito_key"] = socio["distrito"].apply(normalizar)
    socio = socio.drop(columns=[c for c in COLUMNAS_DUPLICADAS if c in socio.columns])
    assert socio["distrito_key"].is_unique, "Hay distritos duplicados en el Excel"
    assert socio["ubigeo"].is_unique
    return socio


def _poblacion_anual(socio, id_cols):
    poblacion = socio[id_cols].copy()
    poblacion["pob_2017"] = socio["pob_censada_2017"]
    for a in range(2018, 2026):
        poblacion[f"pob_{a}"] = socio[f"pob_proyectada_{a}"]

    pob_long = poblacion.melt(
        id_vars=id_cols, value_vars=[f"pob_{a}" for a in ANIOS],
        var_name="anio", value_name="poblacion",
    )
    pob_long["anio"] = pob_long["anio"].str.replace("pob_", "").astype(int)
    return pob_long.set_index(id_cols + ["anio"])


def interpolar_socio(socio):
    """Devuelve panel anual 2017-2025. Variables con solo un año censal (2017 o 2025)
    quedan CONSTANTES en todo el rango — TODO: confirmar si se excluyen o se documentan así."""
    id_cols = ["ubigeo", "departamento", "provincia", "distrito", "distrito_key"]
    pob_cols = [c for c in socio.columns if c.startswith("pob_")]
    resto_cols = [c for c in socio.columns if c not in pob_cols + id_cols]

    patron = re.compile(r"^(.*)_(2017|2025)$")
    pares = {}
    for c in resto_cols:
        m = patron.match(c)
        base, anio = m.group(1), int(m.group(2))
        pares.setdefault(base, {})[anio] = c

    frames = [_poblacion_anual(socio, id_cols)]

    for base, d in pares.items():
        tabla = pd.DataFrame(index=socio.index)
        if len(d) == 2:
            v17, v25 = socio[d[2017]].values, socio[d[2025]].values
            for a in ANIOS:
                frac = (a - 2017) / (2025 - 2017)
                tabla[a] = v17 + (v25 - v17) * frac
        else:
            anio_disp = list(d.keys())[0]
            val = socio[d[anio_disp]].values
            for a in ANIOS:
                tabla[a] = val

        tabla[id_cols] = socio[id_cols]
        tabla_long = tabla.melt(id_vars=id_cols, value_vars=ANIOS, var_name="anio", value_name=base)
        tabla_long["anio"] = tabla_long["anio"].astype(int)
        frames.append(tabla_long.set_index(id_cols + ["anio"]))

    return pd.concat(frames, axis=1).reset_index()