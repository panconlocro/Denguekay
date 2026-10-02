"""Reevaluación transaccional desde la BD, sin entrenar ni leer datos externos."""

from time import perf_counter
from uuid import uuid4

import pandas as pd
from sqlalchemy import select

from src.db.modelos import EjecucionPrediccion, Prediccion, VersionModelo
from src.serving.artefactos import huella_json
from src.serving.publicacion import (activar_versiones_servicio, actualizar_alertas,
                                     construir_predicciones_vigentes)
from src.serving.riesgo import disponibilidad_modelo


class ReevaluacionNoDisponible(ValueError):
    """Impide publicar cambios incompletos, incompatibles o con fuga temporal."""


def ultima_ejecucion_vigente(sesion, horizonte):
    """Última publicación completada con filas vigentes para ese horizonte."""
    return sesion.scalar(select(EjecucionPrediccion).where(
        EjecucionPrediccion.estado == "completada",
        select(Prediccion.id).where(Prediccion.ejecucion_id == EjecucionPrediccion.id,
            Prediccion.horizonte == horizonte, Prediccion.tipo == "vigente").exists()
    ).order_by(EjecucionPrediccion.fecha.desc(), EjecucionPrediccion.id.desc()).limit(1))


def reevaluar(sesion, horizonte, cfg, candidata=None):
    """Crea otra ejecución preservando versiones, predicciones y alertas previas.

    El llamador confirma o revierte la transacción completa. Solo reevalúa
    filas vigentes: nunca sustituye una predicción OOS por un ajuste posterior.
    Bloquea las versiones del horizonte para serializar escrituras en Postgres.
    """
    inicio = perf_counter()
    bloqueadas = list(sesion.scalars(select(VersionModelo).where(
        VersionModelo.horizonte == horizonte, VersionModelo.origen == "servicio"
    ).order_by(VersionModelo.id).with_for_update().execution_options(populate_existing=True)))
    versiones = {v.tipo: v for v in bloqueadas if v.activa}
    if candidata is not None:
        if candidata.horizonte != horizonte or not candidata.puede_activarse:
            raise ReevaluacionNoDisponible("La versión histórica no tiene un artefacto de servicio reactivable")
        versiones[candidata.tipo] = candidata
    if set(versiones) != {"clasificacion", "regresion", "persistencia"}:
        raise ReevaluacionNoDisponible("Faltan versiones activas para el horizonte solicitado")
    for version in versiones.values():
        disponible = disponibilidad_modelo(version, cfg.servir_no_validadas)
        if not disponible["disponible"]:
            raise ReevaluacionNoDisponible(disponible["motivo"])
    fuente = ultima_ejecucion_vigente(sesion, horizonte)
    if fuente is None:
        raise ReevaluacionNoDisponible("No hay vectores vigentes publicados para recalcular")
    anteriores = list(sesion.scalars(select(Prediccion).where(
        Prediccion.ejecucion_id == fuente.id, Prediccion.horizonte == horizonte,
        Prediccion.tipo == "vigente").order_by(Prediccion.ubigeo)))
    filas = []
    for p in anteriores:
        filas.append({**p.caracteristicas, "ubigeo": p.ubigeo, "anio": p.anio,
            "semana": p.semana, "semana_inicio": pd.Timestamp(p.semana_inicio),
            "origen_cierre": pd.Timestamp(p.origen_cierre)})
    claves = {(horizonte, t, "servicio"): v for t, v in versiones.items()}
    try:
        registros = construir_predicciones_vigentes({horizonte: pd.DataFrame(filas)}, claves, cfg)
    except (ValueError, KeyError, TypeError) as error:
        raise ReevaluacionNoDisponible(str(error)) from error
    entradas = {"ejecucion_fuente": fuente.id,
                "vectores_sha256": huella_json(filas),
                "versiones": sorted(v.id for v in versiones.values()),
                "riesgo": cfg.riesgo, "alerta_nivel_minimo": cfg.alerta_nivel_minimo}
    operacion = "activacion_api" if candidata is not None else "reevaluacion_api"
    ejecucion = EjecucionPrediccion(fecha_corte_datos=fuente.fecha_corte_datos,
        versiones_usadas=entradas["versiones"], hashes_entrada=entradas,
        huella=huella_json({**entradas, "solicitud": uuid4().hex}),
        estado="en_proceso", filas_generadas=0, duracion_segundos=0, resumen={})
    sesion.add(ejecucion)
    sesion.flush()
    activar_versiones_servicio(sesion, claves, ejecucion.id,
                              motivo="Activación controlada desde la API; selección para inferencia")
    sesion.execute(Prediccion.__table__.insert(), [
        {**r, "ejecucion_id": ejecucion.id} for r in registros])
    alertas = actualizar_alertas(sesion, ejecucion.id, (horizonte,), cfg)
    ejecucion.estado = "completada"
    ejecucion.filas_generadas = len(registros)
    ejecucion.duracion_segundos = perf_counter() - inicio
    ejecucion.resumen = {"ejecucion_id": ejecucion.id, "operacion": operacion,
        "horizonte": horizonte, "fecha_corte_datos": str(fuente.fecha_corte_datos),
        "fecha_actualizacion": ejecucion.fecha.isoformat(),
        "filas_generadas": len(registros), "versiones_usadas": entradas["versiones"],
        "alertas": alertas, "duracion_segundos": ejecucion.duracion_segundos,
        "estado_validacion": "validado" if all(versiones[t].estado_validacion == "validado"
            for t in ("clasificacion", "regresion")) else "experimental"}
    sesion.flush()
    return ejecucion.resumen
