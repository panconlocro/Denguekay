"""Variables climáticas causales para una semana objetivo distrital.

La climatología se ajusta por corte temporal. La anomalía descriptiva del EDA
usa todos los años y no debe emplearse directamente para pronosticar.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.validation.contrato_pronostico import CLAVE, auditar_origen


CLIMA_PRINCIPAL = ("hum_rel_media", "precip_total_mm")
CLIMA_CANDIDATO = ("temp_min",)


@dataclass(frozen=True)
class Climatologia:
    """Medias por distrito y semana estimadas con clima disponible al corte."""

    tabla: pd.DataFrame
    fecha_corte: pd.Timestamp
    variables: tuple[str, ...]


def _validar_clima(panel: pd.DataFrame, variables: tuple[str, ...]) -> pd.DataFrame:
    faltan = set(variables) - set(panel)
    if faltan:
        raise ValueError(f"Faltan variables climáticas: {sorted(faltan)}")
    audit = auditar_origen(panel, 1)
    datos = audit.merge(panel[CLAVE + list(variables)], on=CLAVE,
                        how="left", validate="one_to_one", sort=False)
    if len(datos) != len(panel):
        raise ValueError("El cruce climático cambió el número de filas")
    for variable in variables:
        valores = pd.to_numeric(datos[variable], errors="raise")
        if valores.isna().any() or not np.isfinite(valores.to_numpy(float)).all():
            raise ValueError(f"{variable} debe ser numérica, finita y completa")
        datos[variable] = valores
    semana = pd.to_numeric(datos["semana"], errors="raise")
    if semana.isna().any() or not semana.between(1, 53).all() or not (semana % 1 == 0).all():
        raise ValueError("semana debe ser un entero entre 1 y 53")
    datos["semana_clima"] = semana.clip(upper=52).astype(int)
    return datos


def ajustar_climatologia(
    panel: pd.DataFrame,
    fecha_corte: str | pd.Timestamp,
    variables: tuple[str, ...] = CLIMA_PRINCIPAL,
) -> Climatologia:
    """Ajusta medias distrito × semana solo con semanas cerradas al corte.

    ``fecha_corte`` debe ser la fecha de cierre del primer origen de la
    validación, no la última fecha del panel. La semana 53 comparte casilla
    climatológica con la 52, siguiendo la convención descriptiva del EDA.
    """
    if not variables or len(set(variables)) != len(variables):
        raise ValueError("Indique variables climáticas distintas")
    corte = pd.Timestamp(fecha_corte)
    if pd.isna(corte):
        raise ValueError("fecha_corte inválida")
    datos = _validar_clima(panel, variables)
    entrenamiento = datos.loc[datos["semana_inicio"] + pd.Timedelta(days=6) <= corte]
    if entrenamiento.empty:
        raise ValueError("No hay semanas climáticas cerradas antes del corte")
    tabla = entrenamiento.groupby(["ubigeo", "semana_clima"], as_index=False)[list(variables)].mean()
    # Evita aplicar una climatología de otro distrito o de semanas sin historia.
    esperadas = datos[["ubigeo", "semana_clima"]].drop_duplicates()
    cobertura = esperadas.merge(tabla[["ubigeo", "semana_clima"]], on=["ubigeo", "semana_clima"],
                                how="left", indicator=True, validate="one_to_one")
    if cobertura["_merge"].ne("both").any():
        ejemplo = cobertura.loc[cobertura["_merge"].ne("both"), ["ubigeo", "semana_clima"]].head().to_dict("records")
        raise ValueError(f"Climatología sin historia para distrito-semana: {ejemplo}")
    return Climatologia(tabla, corte, variables)


def construir_clima(
    panel: pd.DataFrame, horizonte: int, climatologia: Climatologia,
    ventana: int = 5,
) -> pd.DataFrame:
    """Crea medias crudas y anomalías de ``t-h-ventana+1`` a ``t-h``.

    En h=4 y ventana=5, la ventana usa t−8,…,t−4. Las primeras h+4
    filas por distrito permanecen sin historia. No se crean salidas para la
    precipitación duplicada ``lluvia_total_mm``.
    """
    if horizonte not in (2, 4) or ventana < 2:
        raise ValueError("Use horizonte 2 o 4 y ventana de al menos 2 semanas")
    datos = _validar_clima(panel, climatologia.variables)
    tabla = climatologia.tabla
    esperadas = {"ubigeo", "semana_clima", *climatologia.variables}
    if not esperadas.issubset(tabla) or tabla.duplicated(["ubigeo", "semana_clima"]).any():
        raise ValueError("La climatología tiene columnas faltantes o llaves duplicadas")
    datos = datos.merge(tabla, on=["ubigeo", "semana_clima"], how="left",
                        suffixes=("", "_climatologia"), validate="many_to_one", sort=False)
    if len(datos) != len(panel):
        raise ValueError("La climatología cambió el número de filas")
    salida = datos[CLAVE + ["semana_inicio"]].copy()
    for variable in climatologia.variables:
        base = datos[f"{variable}_climatologia"]
        if base.isna().any() or not np.isfinite(base.to_numpy(float)).all():
            raise ValueError(f"Climatología incompleta para {variable}")
        for tipo, valores in (("media", datos[variable]), ("anomalia_media", datos[variable] - base)):
            rolling = valores.groupby(datos["ubigeo"], sort=False).transform(
                lambda s: s.rolling(ventana, min_periods=ventana).mean()
            )
            salida[f"{variable}_{tipo}{ventana}_h{horizonte}"] = (
                rolling.groupby(datos["ubigeo"], sort=False).shift(horizonte)
            )
    return salida


def construir_clima_observado(
    panel: pd.DataFrame, horizonte: int, ventana: int = 5,
    variables: tuple[str, ...] = CLIMA_PRINCIPAL,
) -> pd.DataFrame:
    """Crea medias climáticas causales sin ajustar una climatología global.

    Sirve para publicar candidatos en gold antes de definir los folds. Las
    anomalías siguen construyéndose con ``ajustar_climatologia`` y
    ``construir_clima`` dentro de cada corte de entrenamiento.
    """
    if horizonte not in (2, 4) or ventana < 2 or not variables or len(set(variables)) != len(variables):
        raise ValueError("Use horizonte 2 o 4, ventana >= 2 y variables distintas")
    datos = _validar_clima(panel, variables)
    salida = datos[CLAVE + ["semana_inicio"]].copy()
    for variable in variables:
        rolling = datos[variable].groupby(datos["ubigeo"], sort=False).transform(
            lambda s: s.rolling(ventana, min_periods=ventana).mean()
        )
        salida[f"{variable}_media{ventana}_h{horizonte}"] = (
            rolling.groupby(datos["ubigeo"], sort=False).shift(horizonte)
        )
    return salida
