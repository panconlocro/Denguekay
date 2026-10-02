"""Publicación transaccional y conservación del historial de predicciones."""

from collections import Counter

import numpy as np
import pandas as pd
from sqlalchemy import select, update

from src.db.modelos import (ActivacionModelo, Alerta, EjecucionPrediccion, ImportanciaVariable,
                            Prediccion, VersionModelo, ahora_utc)
from src.serving.artefactos import predecir_con_version
from src.serving.riesgo import genera_alerta, nivel_riesgo
from src.validation.contrato_pronostico import CLAVE


def guardar_versiones(sesion, preparadas, mlflow_run_id):
    """Una huella reutiliza la versión; sus métricas/booster no se sobrescriben."""
    existentes = {v.huella: v for v in sesion.scalars(select(VersionModelo))}
    resultado = {}
    for clave, candidata in preparadas.items():
        valores = dict(candidata.datos)
        version = existentes.get(valores["huella"])
        if version is None:
            if valores["origen"] == "servicio":
                valores["mlflow_run_id"] = mlflow_run_id
            version = VersionModelo(**valores)
            sesion.add(version)
            sesion.flush()
            for importancia in candidata.importancias:
                sesion.add(ImportanciaVariable(version_modelo_id=version.id, **importancia))
            existentes[version.huella] = version
        resultado[clave] = version
    sesion.flush()
    return resultado


def activar_versiones_servicio(sesion, versiones, ejecucion_id,
                              motivo="Publicación batch de una versión de servicio"):
    """Retira la selección previa antes de activar otra, con auditoría de cambio."""
    for (h, tipo, bloque), nueva in versiones.items():
        if bloque != "servicio":
            continue
        if not nueva.puede_activarse:
            raise ValueError("No puede activarse una versión histórica sin artefacto de servicio")
        anterior = sesion.scalar(select(VersionModelo).where(
            VersionModelo.horizonte == h, VersionModelo.tipo == tipo, VersionModelo.activa.is_(True)))
        if anterior is not None and anterior.id == nueva.id:
            continue
        if anterior is not None:
            anterior.activa = False
            sesion.flush()
        nueva.activa = True
        sesion.add(ActivacionModelo(version_anterior_id=anterior.id if anterior else None,
            version_nueva_id=nueva.id, ejecucion_id=ejecucion_id, motivo=motivo))
        sesion.flush()


def construir_predicciones_vigentes(futuros, versiones, cfg):
    """Evalúa los boosters guardados y exige ajuste anterior o igual al origen."""
    registros = []
    for h, filas in futuros.items():
        if filas.empty:
            continue
        modelos = {t: versiones[h, t, "servicio"] for t in ("clasificacion", "regresion", "persistencia")}
        for modelo in modelos.values():
            if not filas.origen_cierre.ge(pd.Timestamp(modelo.entrenamiento_corte)).all():
                raise ValueError("El modelo usa etiquetas cerradas después del origen de una predicción")
        columnas = sorted(set(c for m in modelos.values() for c in m.columnas))
        vectores = filas[columnas].to_dict("records")
        probabilidades = predecir_con_version(modelos["clasificacion"], vectores)
        conteos = predecir_con_version(modelos["regresion"], vectores)
        persistencia = predecir_con_version(modelos["persistencia"], vectores)
        for i, fila in enumerate(filas.itertuples()):
            registros.append(_registro(fila, h, "vigente", modelos, vectores[i],
                float(probabilidades[i]), float(conteos[i]), float(persistencia[i]), cfg))
    return registros


def construir_predicciones_retrospectivas(protocolo, horizontes, versiones, cfg):
    """Combina los dos objetivos de Rosa sobre sus mismas llaves OOS."""
    registros = []
    for h in horizontes:
        datos = protocolo.datos[h].set_index(CLAVE)
        for bloque in ("temporada_2022", "temporada_2023", "temporada_2024", "calendario_2025"):
            modelos = {t: versiones[h, t, bloque] for t in ("clasificacion", "regresion", "persistencia")}
            base = protocolo.predicciones.loc[protocolo.predicciones.horizonte.eq(h)
                                              & protocolo.predicciones.bloque.eq(bloque)]
            cls = base.loc[base.variante.eq(cfg.variantes["clasificacion"])].set_index(CLAVE).sort_index()
            reg = base.loc[base.variante.eq(cfg.variantes["regresion"])].set_index(CLAVE).sort_index()
            if not cls.index.equals(reg.index):
                raise ValueError("Clasificación y regresión OOS no comparten las mismas semanas")
            fuente = datos.loc[cls.index]
            columnas = sorted(set(c for m in modelos.values() for c in m.columnas))
            vectores = fuente[columnas].to_dict("records")
            for i, fila in enumerate(cls.reset_index().itertuples()):
                if any(pd.Timestamp(m.entrenamiento_corte) > fila.origen_cierre for m in modelos.values()):
                    raise ValueError("El ajuste histórico es posterior al origen de su predicción")
                registros.append(_registro(fila, h, "retrospectiva", modelos, vectores[i],
                    float(fila.probabilidad_brote), float(reg.casos_predichos.iloc[i]),
                    float(vectores[i][f"casos_lag_{h}"]), cfg))
    return registros


def _registro(fila, h, tipo, versiones, vector, prob, casos, persistencia, cfg):
    if not np.isfinite([prob, casos, persistencia]).all() or min(casos, persistencia) < 0:
        raise ValueError("No se publican predicciones no finitas o conteos negativos")
    if (fila.semana_inicio - fila.origen_cierre).days != 7 * h - 6:
        raise ValueError("La predicción no respeta el origen t-h")
    return {"ubigeo": fila.ubigeo, "horizonte": h, "anio": int(fila.anio), "semana": int(fila.semana),
            "semana_inicio": fila.semana_inicio.date(), "origen_cierre": fila.origen_cierre.date(),
            "probabilidad": prob, "nivel_riesgo": nivel_riesgo(prob, cfg.riesgo),
            "casos_estimados": casos, "casos_persistencia": persistencia,
            "alerta_modelo": prob >= versiones["clasificacion"].umbral_probabilidad, "tipo": tipo,
            "version_clasificacion_id": versiones["clasificacion"].id,
            "version_regresion_id": versiones["regresion"].id,
            "version_persistencia_id": versiones["persistencia"].id,
            "caracteristicas": {c: float(v) for c, v in vector.items()}, "motivo": None}


def actualizar_alertas(sesion, ejecucion_id, horizontes, cfg):
    """Retira alertas anteriores y crea avisos actuales o históricos auditables."""
    ahora = ahora_utc()
    retiradas = sesion.execute(update(Alerta).where(Alerta.horizonte.in_(horizontes),
        Alerta.estado == "activa").values(estado="retirada", fecha_retiro=ahora,
        motivo=f"Sustituida por la ejecución {ejecucion_id}"))
    nuevas = []
    campos = (Prediccion.id, Prediccion.ubigeo, Prediccion.horizonte,
              Prediccion.semana_inicio, Prediccion.nivel_riesgo, Prediccion.tipo)
    for pred in sesion.execute(select(*campos).where(Prediccion.ejecucion_id == ejecucion_id)):
        if not genera_alerta(pred.nivel_riesgo, cfg.alerta_nivel_minimo):
            continue
        retrospectiva = pred.tipo == "retrospectiva"
        nuevas.append({"prediccion_id": pred.id, "ubigeo": pred.ubigeo, "horizonte": pred.horizonte,
                       "semana_inicio": pred.semana_inicio, "nivel": pred.nivel_riesgo,
                       "estado": "retirada" if retrospectiva else "activa", "fecha_generacion": ahora,
                       "fecha_retiro": ahora if retrospectiva else None,
                       "motivo": "Predicción retrospectiva; no constituye alerta vigente" if retrospectiva else None})
    if nuevas:
        sesion.execute(Alerta.__table__.insert(), nuevas)
    return {"retiradas_anteriores": retiradas.rowcount,
            "activas_nuevas": sum(r["estado"] == "activa" for r in nuevas),
            "historicas_nuevas": sum(r["estado"] == "retirada" for r in nuevas)}


def publicar_lote(sesion, ejecucion_id, preparadas, futuros, protocolo, horizontes,
                  cfg, mlflow_run_id, no_disponibles, duracion):
    """Hace visibles modelos, predicciones y alertas en una sola transacción."""
    ejecucion = sesion.scalar(select(EjecucionPrediccion).where(EjecucionPrediccion.id == ejecucion_id).with_for_update())
    if ejecucion is None:
        raise ValueError("No existe la ejecución de publicación")
    if ejecucion.estado == "completada":
        return {**ejecucion.resumen, "reutilizada": True}
    versiones = guardar_versiones(sesion, preparadas, mlflow_run_id)
    activar_versiones_servicio(sesion, versiones, ejecucion_id)
    registros = construir_predicciones_vigentes(futuros, versiones, cfg)
    registros += construir_predicciones_retrospectivas(protocolo, horizontes, versiones, cfg)
    if registros:
        sesion.execute(Prediccion.__table__.insert(), [{**r, "ejecucion_id": ejecucion_id} for r in registros])
    sesion.flush()
    alertas = actualizar_alertas(sesion, ejecucion_id, horizontes, cfg)
    resumen = {"ejecucion_id": ejecucion_id, "reutilizada": False, "mlflow_run_id": mlflow_run_id,
        "fecha_corte_datos": str(ejecucion.fecha_corte_datos), "filas_generadas": len(registros),
        "predicciones_por_tipo": dict(Counter(r["tipo"] for r in registros)), "alertas": alertas,
        "no_disponibles": no_disponibles, "versiones_servicio": [
            {"id": v.id, "horizonte": v.horizonte, "tipo": v.tipo, "variante": v.variante,
             "estado_validacion": v.estado_validacion} for (h, t, b), v in versiones.items() if b == "servicio"]}
    ejecucion.estado = "completada"
    ejecucion.versiones_usadas = sorted({v.id for v in versiones.values()})
    ejecucion.filas_generadas = len(registros)
    ejecucion.duracion_segundos = duracion
    ejecucion.motivo = None
    ejecucion.resumen = resumen
    return resumen
