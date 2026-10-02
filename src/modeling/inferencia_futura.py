"""Filas futuras en memoria con las funciones y el calendario del modelado."""

import numpy as np
import pandas as pd

from src.modeling.features import FECHA_SOCIO_2017
from src.modeling.historia_calendario import construir_historia_calendario
from src.modeling.sociodemografia import referencia_2017, construir_sociodemografia
from src.modeling.validacion_temporal_compacta import variantes_compactas
from src.utils.calendario import semana_epi_mmwr
from src.validation.contrato_pronostico import CLAVE, auditar_origen, observaciones_disponibles


def construir_filas_futuras(panel, horizonte, *, columnas=None, fecha_corte=None, referencia=None):
    """Pronostica el objetivo situado exactamente h semanas después del origen.

    Extiende solo el calendario, con casos NaN. Reutiliza los rezagos y la
    sociodemografía fija; no calcula clima ni población anual futura. Recorta
    el panel al cierre solicitado ANTES de construir variables o referencia.
    Devuelve (filas completas, razones de filas no disponibles).
    """
    variantes = variantes_compactas(horizonte)
    columnas = columnas or variantes["base_6_poblacion_2017"]
    permitidas = set(variantes["base_6_poblacion_2017"])
    if not set(columnas) <= permitidas:
        raise ValueError("La inferencia futura solo admite las variantes compactas del protocolo")
    if panel.empty or not panel.ubigeo.map(lambda x: isinstance(x, str)).all():
        raise ValueError("El panel debe contener UBIGEO como texto")
    if not panel.ubigeo.str.fullmatch(r"[0-9]{6}").all() or panel.duplicated(CLAVE).any():
        raise ValueError("UBIGEO inválido o llaves repetidas en el panel")
    datos = panel.copy()
    datos["semana_inicio"] = pd.to_datetime(datos.semana_inicio)
    corte = pd.Timestamp(fecha_corte) if fecha_corte is not None else datos.semana_inicio.max() + pd.Timedelta(days=6)
    if pd.isna(corte) or corte.dayofweek != 5:
        raise ValueError("El corte de datos debe ser un cierre semanal de sábado")
    origen = corte.normalize() - pd.Timedelta(days=6)
    datos = datos.loc[(datos.semana_inicio + pd.Timedelta(days=6)).le(corte)].copy()
    if datos.empty:
        raise ValueError("No hay observaciones cerradas al corte solicitado")
    calendario = semana_epi_mmwr(datos.semana_inicio)
    if not (calendario.anio_epi.eq(datos.anio).all() and calendario.semana_epi.eq(datos.semana).all()):
        raise ValueError("El panel no coincide con el calendario MMWR")
    ref = (referencia if referencia is not None else referencia_2017(datos)) if "log_poblacion_censo_2017" in columnas else None
    filas, no_disponibles = [], []
    objetivo = origen + pd.Timedelta(weeks=horizonte)
    cal_objetivo = semana_epi_mmwr(pd.Series([objetivo])).iloc[0]
    for ubigeo, distrito in datos.groupby("ubigeo", sort=True):
        motivo = None
        if distrito.semana_inicio.max() != origen:
            motivo = "El distrito no tiene observación para la semana de origen"
        elif ref is not None and not ref.ubigeo.eq(ubigeo).any():
            motivo = "No hay referencia censal de 2017 para el distrito"
        else:
            fechas = pd.date_range(distrito.semana_inicio.max() + pd.Timedelta(weeks=1), objetivo, freq="7D")
            cal = semana_epi_mmwr(pd.Series(fechas))
            futuros = pd.DataFrame({"ubigeo": ubigeo, "anio": cal.anio_epi,
                                    "semana": cal.semana_epi, "semana_inicio": fechas,
                                    "casos_Dengue": np.nan})
            extendido = pd.concat([distrito, futuros], ignore_index=True)
            try:
                audit = auditar_origen(extendido, horizonte)
            except ValueError:
                motivo = "Historia semanal incompleta o fechas repetidas en el distrito"
            if motivo is None:
                historia = construir_historia_calendario(extendido, horizonte, permitir_faltantes=True)
                if ref is not None:
                    socio = construir_sociodemografia(extendido, horizonte,
                        ref.loc[ref.ubigeo.eq(ubigeo)], FECHA_SOCIO_2017)
                    historia = historia.merge(socio[CLAVE + ["log_poblacion_censo_2017"]],
                                               on=CLAVE, validate="one_to_one")
                fila = historia.loc[historia.semana_inicio.eq(objetivo)].copy()
                if len(fila) != 1 or fila[columnas].isna().any().any() or not np.isfinite(fila[columnas].to_numpy(float)).all():
                    motivo = "No hay historia suficiente o referencia disponible para las variables del modelo"
                else:
                    origen_auditado = audit.loc[audit.semana_inicio.eq(objetivo)]
                    if not observaciones_disponibles(origen_auditado,
                            pd.Series([origen]), pd.Series([corte])).all():
                        raise ValueError("La información no estaba disponible al origen del pronóstico")
                    if not fila.origen_cierre.eq(corte).all():
                        raise ValueError("La fila futura no respeta el cierre de origen solicitado")
                    filas.append(fila)
        if motivo:
            no_disponibles.append({"ubigeo": ubigeo, "horizonte": horizonte,
                "anio": int(cal_objetivo.anio_epi), "semana": int(cal_objetivo.semana_epi),
                "semana_inicio": str(objetivo.date()), "disponible": False, "motivo": motivo})
    campos = [*CLAVE, "semana_inicio", "origen_inicio", "origen_cierre", *columnas]
    salida = pd.concat(filas, ignore_index=True)[campos] if filas else pd.DataFrame(columns=campos)
    return salida, no_disponibles
