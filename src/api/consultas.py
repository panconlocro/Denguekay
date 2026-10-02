"""Consultas y DTO basados exclusivamente en registros de la base de datos."""

from datetime import timedelta
from functools import lru_cache

import pandas as pd
from sqlalchemy import case, func, select
from sqlalchemy.orm import joinedload

from src.api.errores import ErrorAPI
from src.db.modelos import (Alerta, CargaDatos, Distrito, EjecucionPrediccion,
    ImportanciaVariable, ObservacionSemanal, Prediccion, VersionModelo)
from src.serving.artefactos import huella_json
from src.serving.reevaluacion import ultima_ejecucion_vigente
from src.serving.riesgo import disponibilidad_modelo, genera_alerta, nivel_riesgo
from src.utils.calendario import semana_epi_mmwr


def metadatos(sesion, disponible=True, motivo=None):
    if "metadatos_api" not in sesion.info:
        carga = sesion.scalar(select(CargaDatos).order_by(CargaDatos.id.desc()).limit(1))
        ejecucion = sesion.scalar(select(EjecucionPrediccion).where(
            EjecucionPrediccion.estado == "completada").order_by(EjecucionPrediccion.id.desc()).limit(1))
        sesion.info["metadatos_api"] = {"fecha_corte_datos": carga.fecha_corte_datos if carga else None,
            "fecha_actualizacion": ejecucion.fecha if ejecucion else (carga.fecha if carga else None),
        }
    return {**sesion.info["metadatos_api"], "disponible": disponible, "motivo": motivo}


def metadatos_predicciones(sesion, fuente):
    """La actualización de otro horizonte no cambia la fecha del lote consultado."""
    return {**metadatos(sesion),
        "fecha_corte_datos": fuente.fecha_corte_datos if fuente else metadatos(sesion)["fecha_corte_datos"],
        "fecha_actualizacion": fuente.fecha if fuente else None}


def paginar(sesion, consulta, pagina, tamano, transformar):
    total = sesion.scalar(select(func.count()).select_from(consulta.order_by(None).subquery()))
    filas = sesion.scalars(consulta.offset((pagina - 1) * tamano).limit(tamano)).all()
    return {**metadatos(sesion, bool(total), None if total else "No hay registros para el filtro solicitado"),
            "elementos": [transformar(f) for f in filas], "total": total,
            "pagina": pagina, "tamano_pagina": tamano}


def distrito_existente(sesion, ubigeo):
    if "distritos_api" not in sesion.info:
        sesion.info["distritos_api"] = {d.ubigeo: d for d in sesion.scalars(select(Distrito))}
    distrito = sesion.info["distritos_api"].get(ubigeo)
    if distrito is None:
        raise ErrorAPI(404, "distrito_no_encontrado", "El distrito no existe")
    return distrito


def distrito_dto(d, meta):
    return {**meta, "disponible": True, "motivo": None,
            "ubigeo": d.ubigeo, "distrito": d.nombre, "provincia": d.provincia,
            "lat": d.lat, "lon": d.lon, "geometria": d.geometria,
            "motivo_geometria": d.motivo_geometria, "fecha_actualizacion": d.fecha_actualizacion}


def geojson(sesion):
    """Usa polígonos guardados o centroides reales declarados como puntos."""
    features = []
    for d in sesion.scalars(select(Distrito).order_by(Distrito.ubigeo)):
        geometria = d.geometria
        if geometria is None and d.lat is not None and d.lon is not None:
            geometria = {"type": "Point", "coordinates": [d.lon, d.lat]}
        features.append({"type": "Feature", "id": d.ubigeo, "geometry": geometria,
            "properties": {"ubigeo": d.ubigeo, "distrito": d.nombre, "provincia": d.provincia,
                "representacion": "geometria" if d.geometria else ("centroide" if geometria else "sin_geometria"),
                "motivo_geometria": d.motivo_geometria}})
    return {**metadatos(sesion, bool(features), None if features else "No hay distritos cargados"),
            "type": "FeatureCollection", "features": features}


def modelo_existente(sesion, identificador):
    modelo = sesion.get(VersionModelo, identificador)
    if modelo is None:
        raise ErrorAPI(404, "modelo_no_encontrado", "La versión de modelo no existe")
    return modelo


def modelo_dto(v, meta, detalle=False):
    columnas = ("id", "horizonte", "tipo", "variante", "origen", "bloque", "activa",
                "motivo_artefacto", "umbral_probabilidad", "entrenamiento_inicio",
                "entrenamiento_corte", "fecha_creacion", "mlflow_run_id", "device",
                "version_xgboost", "plataforma")
    resultado = {**meta, **{c: getattr(v, c) for c in columnas},
                 "disponible": True, "motivo": None, "fecha_actualizacion": v.fecha_creacion}
    resultado.update(estado_validacion=v.estado_validacion, puede_activarse=v.puede_activarse,
        artefacto_disponible=v.artefacto is not None,
        nota_activacion="Activa indica selección para inferencia; no acredita promoción ni validación de producción")
    if detalle:
        for c in ("columnas", "hiperparametros", "metricas_evaluacion", "criterios_validacion",
                  "particion_temporal", "sha256_gold", "sha256_manifiesto"):
            resultado[c] = getattr(v, c)
        resultado.update(detalle_validacion=v.detalle_validacion,
                         sha256_artefacto=huella_json(v.artefacto) if v.artefacto is not None else None)
    return resultado


def salud(sesion):
    sesion.execute(select(1)).one()
    ejecucion = sesion.scalar(select(EjecucionPrediccion).where(
        EjecucionPrediccion.estado == "completada").order_by(EjecucionPrediccion.id.desc()).limit(1))
    return {**metadatos(sesion), "estado": "operativa", "conexion_bd": True,
        "versiones_activas": [modelo_dto(v, metadatos(sesion)) for v in sesion.scalars(select(VersionModelo).where(
            VersionModelo.activa.is_(True)).order_by(VersionModelo.horizonte, VersionModelo.tipo))],
        "ultima_ejecucion": {"id": ejecucion.id, "fecha": ejecucion.fecha,
            "estado": ejecucion.estado, "filas_generadas": ejecucion.filas_generadas} if ejecucion else None}


@lru_cache(maxsize=4096)
def numero_semana(fecha):
    resultado = semana_epi_mmwr(pd.Series([pd.Timestamp(fecha)])).iloc[0]
    return int(resultado.anio_epi), int(resultado.semana_epi)


def observacion_dto(o, d, meta, fecha=None):
    fecha = o.semana_inicio if o else fecha
    anio, semana = (o.anio, o.semana) if o else numero_semana(fecha)
    disponible = o is not None and o.casos is not None
    return {"ubigeo": d.ubigeo, "distrito": d.nombre, "anio": anio, "semana_epi": semana,
        "semana_inicio": fecha, "horizonte": None, "tipo_dato": "observado",
        "estado_validacion": "no_aplica", "version_modelo_id": None,
        "fecha_actualizacion": o.fecha_actualizacion if o else None,
        "fecha_corte_datos": o.fecha_corte_datos if o else meta["fecha_corte_datos"],
        "casos": o.casos if o else None, "brote": o.brote if o else None,
        "umbral_brote_casos": o.umbral_brote_casos if o else None,
        "procedencia": o.procedencia if o else None, "disponible": disponible,
        "motivo": None if disponible else (o.motivo if o else "No existe observación para esta semana")}


def prediccion_dto(p, d, cfg, meta, ejecucion=None, fecha=None, horizonte=None):
    fecha = p.semana_inicio if p else fecha
    anio, semana = (p.anio, p.semana) if p else numero_semana(fecha)
    componentes = {}
    for tipo in ("clasificacion", "regresion"):
        version = getattr(p, "version_" + tipo) if p else None
        valor = getattr(p, "probabilidad" if tipo == "clasificacion" else "casos_estimados") if p else None
        estado = disponibilidad_modelo(version, cfg.servir_no_validadas) if p else {
            "disponible": False, "motivo": "No hay predicción publicada para este distrito y semana"}
        if estado["disponible"] and valor is None:
            estado = {"disponible": False, "motivo": (p.motivo if p else None) or "No hay predicción para este componente"}
        componentes[tipo] = estado
    prob = p.probabilidad if componentes["clasificacion"]["disponible"] else None
    casos = p.casos_estimados if componentes["regresion"]["disponible"] else None
    nivel = nivel_riesgo(prob, cfg.riesgo)
    disponible = all(v["disponible"] for v in componentes.values())
    return {"id": p.id if p else None, "ubigeo": d.ubigeo, "distrito": d.nombre,
        "anio": anio, "semana_epi": semana, "semana_inicio": fecha,
        "horizonte": p.horizonte if p else horizonte, "tipo_dato": "pronosticado",
        "tipo": p.tipo if p else None, "origen_cierre": p.origen_cierre if p else None,
        "estado_validacion": p.estado_validacion if p else "sin_modelo",
        "version_modelo_id": p.version_clasificacion_id if p else None,
        "version_regresion_id": p.version_regresion_id if p else None,
        "version_persistencia_id": p.version_persistencia_id if p else None,
        "ejecucion_id": p.ejecucion_id if p else None, "probabilidad": prob,
        "nivel_riesgo": nivel, "casos_estimados": casos,
        "casos_persistencia": p.casos_persistencia if p and disponible else None,
        "alerta_modelo": p.alerta_modelo if prob is not None else None,
        "alerta_visible": genera_alerta(nivel, cfg.alerta_nivel_minimo) if prob is not None else None,
        "fecha_actualizacion": p.fecha_actualizacion if p else None,
        "fecha_corte_datos": ejecucion.fecha_corte_datos if ejecucion else meta["fecha_corte_datos"],
        "disponible": disponible, "motivo": None if disponible else "; ".join(
            dict.fromkeys(v["motivo"] for v in componentes.values() if not v["disponible"])),
        "componentes": componentes}


def consulta_predicciones(sesion, horizonte, ubigeo=None, semana=None, tipo="vigente"):
    """La consulta pública usa la última ejecución del horizonte, sin rescatar filas viejas."""
    fuente = ultima_ejecucion_vigente(sesion, horizonte)
    consulta = select(Prediccion).options(joinedload(Prediccion.version_clasificacion),
        joinedload(Prediccion.version_regresion)).where(Prediccion.horizonte == horizonte,
            Prediccion.tipo == tipo)
    consulta = consulta.where(Prediccion.ejecucion_id == fuente.id) if fuente else consulta.where(False)
    if ubigeo:
        consulta = consulta.where(Prediccion.ubigeo == ubigeo)
    if semana:
        consulta = consulta.where(Prediccion.semana_inicio == semana)
    return consulta.order_by(Prediccion.semana_inicio, Prediccion.ubigeo), fuente


def mapa(sesion, horizonte, cfg):
    consulta, fuente = consulta_predicciones(sesion, horizonte)
    filas = list(sesion.scalars(consulta))
    predicciones = {p.ubigeo: p for p in filas}
    semana = max((p.semana_inicio for p in filas), default=None)
    meta = metadatos_predicciones(sesion, fuente)
    elementos = []
    for d in sesion.scalars(select(Distrito).order_by(Distrito.ubigeo)):
        p = predicciones.get(d.ubigeo)
        dto = prediccion_dto(p, d, cfg, meta, fuente, semana, horizonte) if semana else None
        elementos.append({"distrito": distrito_dto(d, meta), "prediccion": dto,
            "nivel_riesgo": dto["nivel_riesgo"] if dto else "Sin datos",
            "disponible": dto["disponible"] if dto else False,
            "motivo": dto["motivo"] if dto else "No hay predicción publicada para este horizonte"})
    disponible = any(e["disponible"] for e in elementos)
    cortes = [0, cfg.riesgo["medio"], cfg.riesgo["alto"], cfg.riesgo["muy_alto"], 1]
    leyenda = [{"nivel": nivel, "desde_inclusivo": cortes[i], "hasta": cortes[i + 1],
        "hasta_inclusivo": i == 3} for i, nivel in enumerate(("Bajo", "Medio", "Alto", "Muy alto"))]
    leyenda.append({"nivel": "Sin datos", "desde_inclusivo": None, "hasta": None, "hasta_inclusivo": False})
    return {**meta, "disponible": disponible,
        "motivo": None if disponible else "No hay predicciones disponibles para este horizonte",
        "horizonte": horizonte, "semana_objetivo": semana, "leyenda": leyenda,
        "alerta_nivel_minimo": cfg.alerta_nivel_minimo, "distritos": elementos}


def series(sesion, ubigeo, horizonte, desde, hasta, cfg):
    d = distrito_existente(sesion, ubigeo)
    meta = metadatos(sesion)
    consulta = select(Prediccion).options(joinedload(Prediccion.version_clasificacion),
        joinedload(Prediccion.version_regresion)).join(EjecucionPrediccion).where(
        Prediccion.ubigeo == ubigeo, Prediccion.horizonte == horizonte,
        EjecucionPrediccion.estado == "completada")
    vigente, fuente = consulta_predicciones(sesion, horizonte, ubigeo)
    # Historial OOS más última publicación vigente; jamás versiones vigentes sustituidas.
    consulta = consulta.where((Prediccion.tipo == "retrospectiva") |
        ((Prediccion.tipo == "vigente") & (Prediccion.ejecucion_id == fuente.id if fuente else False)))
    observadas = select(ObservacionSemanal).where(ObservacionSemanal.ubigeo == ubigeo)
    for campo, limite, inferior in (("semana_inicio", desde, True), ("semana_inicio", hasta, False)):
        if limite:
            consulta = consulta.where(getattr(Prediccion, campo) >= limite if inferior else getattr(Prediccion, campo) <= limite)
            observadas = observadas.where(getattr(ObservacionSemanal, campo) >= limite if inferior else getattr(ObservacionSemanal, campo) <= limite)
    preds = {p.semana_inicio: p for p in sesion.scalars(consulta.order_by(
        EjecucionPrediccion.fecha, EjecucionPrediccion.id, Prediccion.id))}
    obs = {o.semana_inicio: o for o in sesion.scalars(observadas)}
    fechas = set(preds) | set(obs)
    inicio = desde or min(fechas, default=None)
    final = hasta or max(fechas, default=None)
    elementos = []
    if inicio and final:
        # Los límites de consulta pueden ser cualquier día; las filas empiezan en domingo.
        inicio += timedelta(days=(6 - inicio.weekday()) % 7)
        if (final - inicio).days > 7 * 1040:
            raise ErrorAPI(422, "rango_demasiado_amplio", "La serie admite hasta 1040 semanas por consulta")
        ejecuciones = {e.id: e for e in sesion.scalars(select(EjecucionPrediccion).where(
            EjecucionPrediccion.id.in_({p.ejecucion_id for p in preds.values()})))}
        while inicio <= final:
            anio, semana = numero_semana(inicio)
            p = preds.get(inicio)
            elementos.append({"semana_inicio": inicio, "anio": anio, "semana_epi": semana,
                "observado": observacion_dto(obs.get(inicio), d, meta, inicio),
                "pronosticado": prediccion_dto(p, d, cfg, meta,
                    ejecuciones.get(p.ejecucion_id) if p else None, inicio, horizonte)})
            inicio += timedelta(days=7)
    disponible = any(e[k]["disponible"] for e in elementos for k in ("observado", "pronosticado"))
    meta["fecha_actualizacion"] = max(
        [o.fecha_actualizacion for o in obs.values()] + [p.fecha_actualizacion for p in preds.values()], default=None)
    return {**meta, "disponible": disponible, "motivo": None if disponible else "No hay datos en el periodo solicitado",
        "ubigeo": ubigeo, "distrito": d.nombre, "horizonte": horizonte,
        "desde": elementos[0]["semana_inicio"] if elementos else desde,
        "hasta": elementos[-1]["semana_inicio"] if elementos else hasta, "elementos": elementos}


def tablero(sesion, horizonte, cfg):
    datos = mapa(sesion, horizonte, cfg)
    filas = [d["prediccion"] for d in datos["distritos"] if d["prediccion"]]
    probabilidades = [p["probabilidad"] for p in filas if p["probabilidad"] is not None]
    casos = [p["casos_estimados"] for p in filas if p["casos_estimados"] is not None]
    conteos = {n: sum(d["nivel_riesgo"] == n for d in datos["distritos"])
               for n in ("Bajo", "Medio", "Alto", "Muy alto", "Sin datos")}
    def indicador(valor, disponible, motivo="No hay predicciones disponibles para este componente"):
        return {"valor": valor if disponible else None, "disponible": disponible,
                "motivo": None if disponible else motivo}
    completos = bool(filas) and len(casos) == len(datos["distritos"])
    return {k: datos[k] for k in ("fecha_corte_datos", "fecha_actualizacion", "disponible", "motivo", "horizonte", "semana_objetivo")} | {
        "estado_validacion": "sin_modelo" if not filas else ("validado" if all(
            p["estado_validacion"] == "validado" for p in filas) else "experimental"),
        "indicadores": {
            "probabilidad_media_distritos_disponibles": indicador(sum(probabilidades) / len(probabilidades) if probabilidades else None, bool(probabilidades)),
            "casos_estimados_distritos_disponibles": indicador(sum(casos) if casos else None, bool(casos)),
            "casos_estimados_region": indicador(sum(casos) if casos else None, completos, "Falta magnitud estimada para uno o más distritos"),
            "distritos_con_alerta_visible": indicador(sum(genera_alerta(p["nivel_riesgo"], cfg.alerta_nivel_minimo)
                for p in filas if p["probabilidad"] is not None), bool(probabilidades))},
        "niveles_riesgo": conteos, "cobertura": {"distritos": len(datos["distritos"]),
            "con_probabilidad": len(probabilidades), "con_magnitud": len(casos)},
        "nota": "Los agregados parciales indican su cobertura. El periodo corresponde al corte de datos, no a la fecha actual"}


def alerta_dto(sesion, a, cfg):
    p = a.prediccion
    ejecuciones = sesion.info.setdefault("ejecuciones_api", {})
    if p.ejecucion_id not in ejecuciones:
        ejecuciones[p.ejecucion_id] = sesion.get(EjecucionPrediccion, p.ejecucion_id)
    dto = prediccion_dto(p, distrito_existente(sesion, a.ubigeo), cfg,
                        metadatos(sesion), ejecuciones[p.ejecucion_id])
    return {"id": a.id, "ubigeo": a.ubigeo, "distrito": dto["distrito"],
        "horizonte": a.horizonte, "semana_objetivo": a.semana_inicio,
        "nivel": a.nivel if dto["componentes"]["clasificacion"]["disponible"] else None,
        "estado": a.estado, "estado_validacion": a.estado_validacion,
        "fecha_generacion": a.fecha_generacion, "fecha_retiro": a.fecha_retiro,
        "motivo_estado": a.motivo, "indicadores": dto,
        "fecha_corte_datos": dto["fecha_corte_datos"], "fecha_actualizacion": dto["fecha_actualizacion"],
        "disponible": dto["disponible"], "motivo": dto["motivo"]}


def consulta_alertas(horizonte, ubigeo, estado):
    consulta = select(Alerta).options(joinedload(Alerta.prediccion).joinedload(Prediccion.version_clasificacion),
        joinedload(Alerta.prediccion).joinedload(Prediccion.version_regresion))
    for campo, valor in ((Alerta.horizonte, horizonte), (Alerta.ubigeo, ubigeo), (Alerta.estado, estado)):
        if valor is not None:
            consulta = consulta.where(campo == valor)
    return consulta.order_by(case((Alerta.nivel == "Muy alto", 4), (Alerta.nivel == "Alto", 3),
                                 (Alerta.nivel == "Medio", 2), else_=1).desc(), Alerta.semana_inicio.desc(), Alerta.id.desc())


def variables(sesion, identificador):
    v = modelo_existente(sesion, identificador)
    filas = list(sesion.scalars(select(ImportanciaVariable).where(
        ImportanciaVariable.version_modelo_id == v.id).order_by(ImportanciaVariable.rango)))
    return {**metadatos(sesion, bool(filas), None if filas else "Esta versión no tiene importancias gain guardadas"),
        "fecha_actualizacion": v.fecha_creacion,
        "version_modelo_id": v.id, "elementos": [
            {"variable": f.variable, "importancia": f.importancia, "rango": f.rango} for f in filas],
        "nota": "Las importancias gain describen el uso de variables en el modelo; no implican causalidad"}
