"""Historia distrital y calendario conocidos al emitir un pronóstico semanal."""

import numpy as np
import pandas as pd

from src.validation.contrato_pronostico import CLAVE, auditar_origen


def construir_historia_calendario(
    panel: pd.DataFrame, horizonte: int, ventana: int = 4,
) -> pd.DataFrame:
    """Construye candidatos causales por distrito y semana objetivo.

    Para el objetivo ``t``, las observaciones de casos llegan como máximo a
    ``t-horizonte``. La media y el conteo de semanas positivas abarcan
    ``t-horizonte-ventana+1`` a ``t-horizonte``. Las primeras filas con
    historia insuficiente conservan NaN. El calendario de la semana objetivo
    es conocido antes del pronóstico. No se imputan faltantes ni se escribe
    ningún dataset; la disponibilidad efectiva de publicación se audita aparte.
    """
    if horizonte not in (2, 4):
        raise ValueError("El proyecto contempla horizontes de 2 o 4 semanas")
    if ventana < 2:
        raise ValueError("La ventana debe cubrir al menos dos semanas")
    if "casos_Dengue" not in panel:
        raise ValueError("Falta casos_Dengue")

    audit = auditar_origen(panel, horizonte)
    fuente = audit.merge(
        panel[CLAVE + ["casos_Dengue"]], on=CLAVE, how="left",
        validate="one_to_one", sort=False,
    )
    if len(fuente) != len(panel):
        raise ValueError("El cruce con casos cambió el número de filas")
    casos = pd.to_numeric(fuente["casos_Dengue"], errors="raise")
    if casos.isna().any() or not np.isfinite(casos.to_numpy(dtype=float)).all() or (casos < 0).any():
        raise ValueError("casos_Dengue debe ser numérico, finito y no negativo")
    semana = pd.to_numeric(fuente["semana"], errors="raise")
    if semana.isna().any() or not semana.between(1, 53).all() or not (semana % 1 == 0).all():
        raise ValueError("semana debe ser un entero entre 1 y 53")

    salida = fuente[CLAVE + ["semana_inicio", "origen_inicio", "origen_cierre"]].copy()
    grupo = casos.groupby(fuente["ubigeo"], sort=False)
    primero = grupo.shift(horizonte)
    salida[f"casos_lag_{horizonte}"] = primero
    salida[f"casos_lag_{horizonte + 1}"] = grupo.shift(horizonte + 1)
    salida[f"casos_media_{ventana}_h{horizonte}"] = primero.groupby(
        fuente["ubigeo"], sort=False
    ).transform(lambda s: s.rolling(ventana, min_periods=ventana).mean())
    salida[f"casos_semanas_positivas_{ventana}_h{horizonte}"] = (
        primero.gt(0).where(primero.notna()).astype(float)
        .groupby(fuente["ubigeo"], sort=False)
        .transform(lambda s: s.rolling(ventana, min_periods=ventana).sum())
    )

    # La semana 53 ocupa la misma posición circular que la semana 1.
    angulo = 2 * np.pi * ((semana.to_numpy(dtype=float) - 1) % 52) / 52
    salida["semana_epi_seno"] = np.sin(angulo)
    salida["semana_epi_coseno"] = np.cos(angulo)
    return salida
