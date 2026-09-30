"""Rasgos distritales fijos de 2017 y estimaciones anuales reconstruidas.

El silver contiene fracciones interpoladas con el extremo de 2025. Este
módulo conserva la alternativa fija de 2017 y permite ensayar por separado
las series anuales. Estas últimas no representan un backtest en tiempo real.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.validation.contrato_pronostico import CLAVE, auditar_origen
from src.processing.socio_interpolacion import SOCIO_COLUMNS


DIRECTAS = ("fraccion_rural", "fraccion_menores_15", "fraccion_desague_red")


@dataclass(frozen=True)
class EjeUrbano:
    """PCA de las fracciones de 2017 ajustado sobre distritos de entrenamiento."""

    columnas: tuple[str, ...]
    media: pd.Series
    desviacion: pd.Series
    cargas: pd.Series
    varianza_explicada: float
    distritos_ajuste: frozenset[str]


def referencia_2017(panel: pd.DataFrame) -> pd.DataFrame:
    """Extrae una fila por UBIGEO con fracciones y población censal de 2017.

    Exige que cada valor sea constante entre las semanas de 2017 y que todos
    los distritos del panel tengan referencia. No usa años posteriores.
    """
    if panel.empty or "anio" not in panel or "ubigeo" not in panel:
        raise ValueError("El panel no tiene llaves demográficas")
    columnas = tuple(c for c in panel if c.startswith("fraccion_"))
    if len(columnas) != 15 or "poblacion" not in panel:
        raise ValueError("Se esperan las 15 fracciones y poblacion del integrado")
    datos = panel.loc[panel.anio.eq(2017), ["ubigeo", "poblacion", *columnas]].copy()
    if datos.empty or datos.ubigeo.isna().any():
        raise ValueError("No hay referencia distrital de 2017")
    presentes = set(datos.ubigeo.astype(str))
    faltan = set(panel.ubigeo.astype(str)) - presentes
    if faltan:
        raise ValueError(f"Distritos sin referencia de 2017: {sorted(faltan)}")
    numericas = ["poblacion", *columnas]
    for c in numericas:
        datos[c] = pd.to_numeric(datos[c], errors="raise")
    if datos[numericas].isna().any().any() or not np.isfinite(datos[numericas].to_numpy(float)).all():
        raise ValueError("La referencia de 2017 contiene nulos o valores no finitos")
    if (datos.poblacion <= 0).any() or not datos[list(columnas)].ge(0).all().all() or not datos[list(columnas)].le(1).all().all():
        raise ValueError("Población o fracciones de 2017 fuera de rango")
    dispersion = datos.groupby("ubigeo")[numericas].nunique(dropna=False)
    if dispersion.gt(1).any().any():
        raise ValueError("La referencia de 2017 cambia entre semanas de un distrito")
    referencia = datos.drop_duplicates("ubigeo").sort_values("ubigeo").reset_index(drop=True)
    if referencia.ubigeo.duplicated().any():
        raise ValueError("UBIGEO duplicado en la referencia de 2017")
    return referencia


def ajustar_eje_urbano(referencia: pd.DataFrame, distritos_entrenamiento: set[str]) -> EjeUrbano:
    """Ajusta CP1 con fracciones de 2017 solo de distritos de entrenamiento."""
    columnas = tuple(c for c in referencia if c.startswith("fraccion_"))
    if len(columnas) != 15 or referencia.ubigeo.duplicated().any():
        raise ValueError("La referencia requiere 15 fracciones y UBIGEO únicos")
    distrito = {str(x) for x in distritos_entrenamiento}
    observados = set(referencia.ubigeo.astype(str))
    if not distrito or not distrito.issubset(observados):
        raise ValueError("Distritos de entrenamiento vacíos o desconocidos")
    ajuste = referencia.loc[referencia.ubigeo.astype(str).isin(distrito), list(columnas)].astype(float)
    if len(ajuste) < 2 or ajuste.isna().any().any() or not np.isfinite(ajuste.to_numpy()).all():
        raise ValueError("Datos insuficientes para ajustar el eje urbano")
    media = ajuste.mean()
    desviacion = ajuste.std(ddof=1)
    if desviacion.le(0).any():
        raise ValueError("Hay fracciones constantes en el ajuste del eje urbano")
    z = (ajuste - media) / desviacion
    _, singulares, vectores = np.linalg.svd(z.to_numpy(), full_matrices=False)
    cargas = pd.Series(vectores[0], index=columnas)
    # Convención del EDA: mayor equipamiento del hogar = lado positivo.
    if cargas["fraccion_hogares_refrigeradora"] < 0:
        cargas = -cargas
    varianza = float(singulares[0] ** 2 / np.sum(singulares ** 2))
    return EjeUrbano(columnas, media, desviacion, cargas, varianza, frozenset(distrito))


def construir_sociodemografia(
    panel: pd.DataFrame, horizonte: int, referencia: pd.DataFrame,
    fecha_disponible: str | pd.Timestamp, eje: EjeUrbano | None = None,
    *, enmascarar_antes_disponibilidad: bool = True,
) -> pd.DataFrame:
    """Anexa rasgos estáticos de 2017 y audita disponibilidad al origen.

    Por defecto, las filas con origen anterior a ``fecha_disponible`` quedan
    en NaN porque no serían pronósticos históricos válidos. Para usar esas
    filas solo como ejemplos de entrenamiento en un corte posterior, se puede
    desactivar el enmascaramiento. El evaluador debe comprobar por separado
    que los orígenes de prueba sí son posteriores a la disponibilidad.
    CP1 debe provenir de un ajuste del fold de entrenamiento.
    """
    if horizonte not in (2, 4):
        raise ValueError("Use horizonte de 2 o 4 semanas")
    disponible = pd.Timestamp(fecha_disponible)
    if pd.isna(disponible):
        raise ValueError("fecha_disponible inválida")
    if referencia.ubigeo.duplicated().any():
        raise ValueError("UBIGEO duplicado en referencia")
    audit = auditar_origen(panel, horizonte)
    columnas = ["ubigeo", "poblacion", *DIRECTAS]
    if not set(columnas).issubset(referencia):
        raise ValueError("Faltan columnas censales de 2017")
    ref = referencia[columnas].copy()
    for columna in columnas[1:]:
        ref[columna] = pd.to_numeric(ref[columna], errors="raise")
    ref["poblacion"] = pd.to_numeric(ref["poblacion"], errors="raise")
    if ref[columnas[1:]].isna().any().any() or not np.isfinite(ref[columnas[1:]].to_numpy(float)).all():
        raise ValueError("Fracciones censales faltantes o no finitas")
    if not ref[list(DIRECTAS)].ge(0).all().all() or not ref[list(DIRECTAS)].le(1).all().all():
        raise ValueError("Fracciones censales fuera de rango")
    if ref.poblacion.isna().any() or not np.isfinite(ref.poblacion.to_numpy(float)).all() or (ref.poblacion <= 0).any():
        raise ValueError("Población censal faltante o no positiva")
    ref = ref.rename(columns={"poblacion": "poblacion_censo_2017", **{c: f"{c}_2017" for c in DIRECTAS}})
    if eje is not None:
        if not set(eje.columnas).issubset(referencia):
            raise ValueError("Faltan fracciones para transformar el eje urbano")
        puntajes = ((referencia[list(eje.columnas)].astype(float) - eje.media) / eje.desviacion) @ eje.cargas
        if puntajes.isna().any() or not np.isfinite(puntajes.to_numpy(float)).all():
            raise ValueError("El eje urbano tiene puntajes faltantes o no finitos")
        ref["eje_urbano_2017"] = puntajes.to_numpy(float)
    salida = audit[CLAVE + ["semana_inicio", "origen_cierre"]].merge(ref, on="ubigeo", how="left", validate="many_to_one", sort=False)
    if len(salida) != len(panel):
        raise ValueError("El cruce demográfico cambió el número de filas")
    if salida["poblacion_censo_2017"].isna().any():
        raise ValueError("Hay distritos sin correspondencia censal")
    salida["log_poblacion_censo_2017"] = np.log(salida.pop("poblacion_censo_2017"))
    features = [c for c in salida if c.endswith("_2017")]
    if enmascarar_antes_disponibilidad:
        salida.loc[salida.origen_cierre.lt(disponible) | salida.origen_cierre.isna(), features] = np.nan
    return salida.drop(columns="origen_cierre")


def construir_sociodemografia_anual_cruda(panel: pd.DataFrame) -> pd.DataFrame:
    """Valida y devuelve población y fracciones anuales sin ajustar PCA."""
    requeridas = set(CLAVE + ["semana_inicio", *SOCIO_COLUMNS])
    faltan = requeridas - set(panel)
    if faltan:
        raise ValueError(f"Faltan columnas demográficas anuales: {sorted(faltan)}")
    if panel.empty or panel[CLAVE + ["semana_inicio"]].isna().any().any():
        raise ValueError("El panel anual está vacío o tiene llaves faltantes")
    if panel.duplicated(CLAVE).any():
        raise ValueError("Hay llaves distrito-año-semana duplicadas")
    claves = ["ubigeo", "anio"]
    datos = panel[claves + SOCIO_COLUMNS].copy()
    for columna in SOCIO_COLUMNS:
        datos[columna] = pd.to_numeric(datos[columna], errors="raise")
    if datos[SOCIO_COLUMNS].isna().any().any() or not np.isfinite(datos[SOCIO_COLUMNS].to_numpy(float)).all():
        raise ValueError("La demografía anual contiene valores nulos o no finitos")
    fracciones = [c for c in SOCIO_COLUMNS if c != "poblacion"]
    if (datos.poblacion <= 0).any() or not datos[fracciones].ge(0).all().all() or not datos[fracciones].le(1).all().all():
        raise ValueError("La población o las fracciones anuales están fuera de rango")
    dispersion = datos.groupby(claves)[SOCIO_COLUMNS].nunique(dropna=False)
    if dispersion.gt(1).any().any():
        raise ValueError("La demografía anual cambia entre semanas de un distrito-año")
    anual = datos.drop_duplicates(claves).copy()
    anual["log_poblacion_anual"] = np.log(anual.pop("poblacion"))
    anual = anual.rename(columns={c: f"{c}_anual" for c in fracciones})
    salida = panel[CLAVE + ["semana_inicio"]].merge(anual, on=claves, how="left", validate="many_to_one", sort=False)
    if len(salida) != len(panel) or salida["log_poblacion_anual"].isna().any():
        raise ValueError("El cruce demográfico anual perdió o duplicó filas")
    return salida


def construir_sociodemografia_anual(panel: pd.DataFrame, eje: EjeUrbano) -> pd.DataFrame:
    """Añade al valor anual un eje con escala de 2017 ajustada por fold.

    El PCA se ajusta fuera de esta función, en el entrenamiento del fold.
    Aplica la misma escala y cargas de 2017 a cada año; las fracciones
    interpoladas de 2018–2024 incorporan el extremo de 2025 del silver.
    """
    if set(eje.columnas) != set(SOCIO_COLUMNS) - {"poblacion"}:
        raise ValueError("El eje urbano no contiene las 15 fracciones esperadas")
    salida = construir_sociodemografia_anual_cruda(panel)
    columnas_anuales = [f"{c}_anual" for c in eje.columnas]
    escala_media = eje.media.rename(index=lambda c: f"{c}_anual")
    escala_desviacion = eje.desviacion.rename(index=lambda c: f"{c}_anual")
    cargas = eje.cargas.rename(index=lambda c: f"{c}_anual")
    puntajes = ((salida[columnas_anuales] - escala_media) / escala_desviacion) @ cargas
    if puntajes.isna().any() or not np.isfinite(puntajes.to_numpy(float)).all():
        raise ValueError("El eje urbano anual contiene puntajes no finitos")
    salida["eje_urbano_anual"] = puntajes.to_numpy(float)
    return salida
