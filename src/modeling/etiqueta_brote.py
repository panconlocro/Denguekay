"""Etiquetas retrospectivas de semanas distritales con nivel elevado de casos.

La regla estacional se parametriza explícitamente: ninguna elección de umbral
queda implícita por importar este módulo. La historia del Excel anterior al
panel es dispersa y sus ausencias se interpretan como cero, igual que en el
canal endémico exploratorio del EDA; esto no prueba notificación de cero.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.validation.contrato_pronostico import CLAVE


@dataclass(frozen=True)
class ConfiguracionBroteEstacional:
    """Parámetros explícitos de la regla estacional de cinco años."""

    multiplicador: float
    anios_previos: int = 5
    minimo_casos: int = 1


def _validar_casos(datos: pd.DataFrame, nombre: str) -> pd.DataFrame:
    faltan = set(CLAVE + ["casos_Dengue"]) - set(datos)
    if faltan:
        raise ValueError(f"{nombre} carece de columnas: {sorted(faltan)}")
    if datos.empty or datos[CLAVE].isna().any().any():
        raise ValueError(f"{nombre} vacío o con llaves incompletas/duplicadas")
    limpio = datos[CLAVE + ["casos_Dengue"]].copy()
    limpio["ubigeo"] = limpio.ubigeo.astype("string").str.zfill(6)
    if not limpio.ubigeo.str.fullmatch(r"\d{6}").all():
        raise ValueError(f"{nombre} contiene UBIGEO inválido")
    for campo in ("anio", "semana"):
        limpio[campo] = pd.to_numeric(limpio[campo], errors="raise")
    if (limpio["anio"] % 1 != 0).any() or (limpio["semana"] % 1 != 0).any() or not limpio.semana.between(1, 53).all():
        raise ValueError(f"{nombre} contiene años o semanas inválidos")
    limpio["anio"] = limpio.anio.astype(int)
    limpio["semana"] = limpio.semana.astype(int)
    if limpio.duplicated(CLAVE).any():
        raise ValueError(f"{nombre} contiene llaves duplicadas")
    limpio["casos_Dengue"] = pd.to_numeric(limpio.casos_Dengue, errors="raise")
    if limpio.casos_Dengue.isna().any() or not np.isfinite(limpio.casos_Dengue.to_numpy(float)).all() or (limpio.casos_Dengue < 0).any() or (limpio.casos_Dengue % 1 != 0).any():
        raise ValueError(f"{nombre} contiene casos inválidos")
    return limpio


def etiquetar_brote_estacional(
    panel: pd.DataFrame, historia: pd.DataFrame, *,
    multiplicador: float, anios_previos: int = 5, minimo_casos: int = 1,
) -> pd.DataFrame:
    """Marca cada semana con casos > media + k·DE de su misma semana previa.

    Usa los ``anios_previos`` años anteriores del mismo UBIGEO y semana
    epidemiológica (DE muestral, ``ddof=1``). Cada año se calcula solo con
    años estrictamente anteriores. La semana 53 se suma a la 52 para formar
    la referencia, siguiendo la convención del EDA; la fila objetivo conserva
    su semana original. Devuelve umbral y etiqueta alineados con ``panel``.
    ``minimo_casos`` es un piso explícito para marcar semanas positivas.
    """
    if not np.isfinite(multiplicador) or multiplicador <= 0:
        raise ValueError("multiplicador debe ser positivo y finito")
    if (not isinstance(anios_previos, int) or not isinstance(minimo_casos, int)
            or anios_previos < 2 or minimo_casos < 1):
        raise ValueError("anios_previos >= 2 y minimo_casos >= 1 son obligatorios")
    actual = _validar_casos(panel, "panel")
    previo = _validar_casos(historia, "historia")
    primero, ultimo = int(actual.anio.min()), int(actual.anio.max())
    if set(actual.anio) != set(range(primero, ultimo + 1)):
        raise ValueError("El panel tiene años completos ausentes en el periodo de etiquetas")
    if not previo.anio.lt(primero).all():
        raise ValueError("La historia debe terminar antes del primer año del panel")
    distritos = sorted(actual.ubigeo.unique())
    previo = previo.loc[previo.ubigeo.isin(distritos)]
    if previo.empty:
        raise ValueError("La historia no contiene distritos del panel")
    anios_requeridos = set(range(primero - anios_previos, primero))
    if not anios_requeridos.issubset(set(previo.anio)):
        raise ValueError(f"Faltan años de historia en los distritos del panel: {sorted(anios_requeridos - set(previo.anio))}")
    todo = pd.concat([previo, actual], ignore_index=True)
    todo["semana_ref"] = todo.semana.clip(upper=52)
    anual = todo.groupby(["ubigeo", "anio", "semana_ref"], as_index=False).casos_Dengue.sum()
    indice = pd.MultiIndex.from_product(
        [distritos, range(1, 53)], names=["ubigeo", "semana_ref"],
    )
    matriz = anual.pivot(index=["ubigeo", "semana_ref"], columns="anio", values="casos_Dengue")
    matriz = matriz.reindex(index=indice, columns=range(primero - anios_previos, ultimo + 1)).fillna(0)
    salidas = []
    for anio in sorted(actual.anio.unique()):
        ventana = matriz[list(range(anio - anios_previos, anio))]
        umbral = ventana.mean(axis=1) + multiplicador * ventana.std(axis=1, ddof=1)
        salidas.append(umbral.rename(anio))
    tabla = pd.concat(salidas, axis=1).stack().rename("umbral_brote_casos").reset_index()
    tabla = tabla.rename(columns={"level_2": "anio"})
    claves = actual[CLAVE].assign(semana_ref=actual.semana.clip(upper=52))
    salida = claves.merge(tabla, on=["ubigeo", "anio", "semana_ref"], how="left", validate="many_to_one", sort=False)
    if len(salida) != len(panel) or salida.umbral_brote_casos.isna().any():
        raise ValueError("No se pudo asignar umbral a todas las distrito-semanas")
    salida["brote"] = ((actual.casos_Dengue.to_numpy() > salida.umbral_brote_casos.to_numpy())
                       & (actual.casos_Dengue.to_numpy() >= minimo_casos)).astype("int8")
    return salida[CLAVE + ["umbral_brote_casos", "brote"]]
