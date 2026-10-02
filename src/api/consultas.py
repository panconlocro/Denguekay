"""Consultas y DTO desde la BD OE2; los lotes se resuelven sin consultas N+1."""

from datetime import timedelta

from sqlalchemy import func, select

from src.api.errores import ErrorAPI
from src.db.modelos import (Alerta, Distrito, Ejecucion, ImportanciaVariable, ObservacionSemanal,
                            Prediccion, SemanaEpidemiologica, VersionModelo)
from src.serving import parametros
from src.serving.inferencia import MOTIVO_H3, TAREAS, seleccionar_versiones
from src.serving.riesgo import ETIQUETAS, NIVELES

NOTA_EXPERIMENTAL = ("Demo experimental: ningún modelo cumple todavía los umbrales de aceptación; "
                     "las predicciones marcadas experimental: true no son un modelo validado.")


# --- utilidades generales -----------------------------------------------------

def metadatos(sesion, disponible=True, motivo=None):
    """Corte de la última ingesta y fin de la última ejecución exitosa."""
    ingesta = sesion.scalar(select(Ejecucion).where(Ejecucion.tipo == "ingesta", Ejecucion.estado == "exitosa")
                            .order_by(Ejecucion.id_ejecucion.desc()).limit(1))
    fin = sesion.scalar(select(func.max(Ejecucion.fin)).where(Ejecucion.estado == "exitosa"))
    corte = ((ingesta.detalle or {}).get("resumen") or {}).get("fecha_corte_datos") if ingesta else None
    return {"disponible": disponible, "motivo": motivo, "fecha_corte_datos": corte, "fecha_actualizacion": fin}


def paginar(sesion, consulta, pagina, tamano, transformar, meta=None):
    """``transformar`` recibe la lista de filas de la página (lote)."""
    total = sesion.scalar(select(func.count()).select_from(consulta.order_by(None).subquery()))
    filas = list(sesion.scalars(consulta.offset((pagina - 1) * tamano).limit(tamano)))
    meta = meta or metadatos(sesion)
    return {**meta, "elementos": transformar(filas), "total": total, "pagina": pagina, "tamano_pagina": tamano}


def semana_dto(s):
    return None if s is None else {"id_semana": s.id_semana, "anio": s.anio, "semana": s.semana,
                                   "fecha_inicio": s.fecha_inicio, "fecha_fin": s.fecha_fin}


def semanas(sesion, ids):
    ids = set(ids)
    if not ids:
        return {}
    return {s.id_semana: s for s in sesion.scalars(select(SemanaEpidemiologica).where(SemanaEpidemiologica.id_semana.in_(ids)))}


# --- distritos y observaciones ---------------------------------------------------

def distrito_existente(sesion, ubigeo):
    d = sesion.get(Distrito, ubigeo)
    if d is None:
        raise ErrorAPI(404, "distrito_no_encontrado", "El ubigeo no pertenece al catálogo de Piura")
    return d


def distrito_dto(d):
    return {"ubigeo": d.ubigeo, "nombre": d.nombre, "ubigeo_provincia": d.ubigeo_provincia,
            "provincia": d.provincia.nombre, "latitud": d.latitud, "longitud": d.longitud,
            "poblacion_censo_2017": d.poblacion_censo_2017, "activo": d.activo}


def nombres_distritos(sesion):
    return dict(sesion.execute(select(Distrito.ubigeo, Distrito.nombre)).all())


def observacion_dtos(sesion, filas):
    nombres, cal = nombres_distritos(sesion), semanas(sesion, (o.id_semana for o in filas))
    return [{"ubigeo": o.ubigeo, "distrito": nombres[o.ubigeo], "semana": semana_dto(cal[o.id_semana]),
             "casos_dengue": o.casos_dengue, "brote": o.brote, "umbral_brote_casos": o.umbral_brote_casos,
             "temp_media_c": o.temp_media_c, "temp_min_c": o.temp_min_c, "temp_max_c": o.temp_max_c,
             "precip_total_mm": o.precip_total_mm, "hum_rel_media_pct": o.hum_rel_media_pct,
             "fuente_casos": o.fuente_casos, "estado_cobertura": o.estado_cobertura} for o in filas]


def consulta_observaciones(ubigeo=None, desde=None, hasta=None):
    consulta = select(ObservacionSemanal).join(
        SemanaEpidemiologica, SemanaEpidemiologica.id_semana == ObservacionSemanal.id_semana)
    if ubigeo:
        consulta = consulta.where(ObservacionSemanal.ubigeo == ubigeo)
    if desde:
        consulta = consulta.where(SemanaEpidemiologica.fecha_inicio >= desde)
    if hasta:
        consulta = consulta.where(SemanaEpidemiologica.fecha_inicio <= hasta)
    return consulta.order_by(ObservacionSemanal.id_semana, ObservacionSemanal.ubigeo)


# --- predicciones -----------------------------------------------------------------

def ejecuciones_oos(sesion):
    return [e.id_ejecucion for e in sesion.scalars(select(Ejecucion).where(Ejecucion.tipo == "inferencia"))
            if (e.detalle or {}).get("origen") == "oos_protocolo"]


def corte_vigente(sesion, horizonte):
    """Último corte publicado por una inferencia operativa (no por la importación OOS)."""
    consulta = select(func.max(Prediccion.id_semana_corte)).where(Prediccion.horizonte == horizonte)
    oos = ejecuciones_oos(sesion)
    if oos:
        consulta = consulta.where(Prediccion.id_ejecucion.not_in(oos))
    return sesion.scalar(consulta)


def prediccion_dtos(sesion, filas):
    """DTO por lote: semanas, versiones, ejecuciones y persistencia en pocas consultas."""
    if not filas:
        return []
    nombres = nombres_distritos(sesion)
    cal = semanas(sesion, [p.id_semana_corte for p in filas] + [p.id_semana_objetivo for p in filas])
    versiones = {v.id_version: v for v in sesion.scalars(select(VersionModelo))}
    detalles = dict(sesion.execute(select(Ejecucion.id_ejecucion, Ejecucion.detalle).where(
        Ejecucion.id_ejecucion.in_({p.id_ejecucion for p in filas}))).all())
    persistencia = dict(((u, s), c) for u, s, c in sesion.execute(select(
        ObservacionSemanal.ubigeo, ObservacionSemanal.id_semana, ObservacionSemanal.casos_dengue).where(
        ObservacionSemanal.id_semana.in_({p.id_semana_corte for p in filas}),
        ObservacionSemanal.ubigeo.in_({p.ubigeo for p in filas}))))
    vigentes = {h: corte_vigente(sesion, h) for h in {p.horizonte for p in filas}}
    resultado = []
    for p in filas:
        clf, reg = versiones.get(p.id_version_clasificador), versiones.get(p.id_version_regresor)
        usadas = [v for v in (clf, reg) if v is not None]
        experimental = (any(not v.cumple_umbrales for v in usadas) if usadas
                        else bool((detalles.get(p.id_ejecucion) or {}).get("experimental", True)))
        disponible = p.estado == "disponible"
        resultado.append({
            "disponible": disponible, "motivo": p.motivo_no_disponible,
            "id_prediccion": p.id_prediccion, "ubigeo": p.ubigeo, "distrito": nombres[p.ubigeo],
            "horizonte": p.horizonte, "semana_corte": semana_dto(cal[p.id_semana_corte]),
            "semana_objetivo": semana_dto(cal[p.id_semana_objetivo]),
            "tipo": "vigente" if p.id_semana_corte == vigentes[p.horizonte] else "retrospectiva",
            "estado": p.estado, "probabilidad_brote": p.probabilidad_brote, "nivel_riesgo": p.nivel_riesgo,
            "nivel_riesgo_etiqueta": ETIQUETAS.get(p.nivel_riesgo), "casos_estimados": p.casos_estimados,
            "casos_persistencia": persistencia.get((p.ubigeo, p.id_semana_corte)),
            "alerta_modelo": (p.probabilidad_brote >= clf.umbral_probabilidad
                              if disponible and clf is not None and clf.umbral_probabilidad is not None else None),
            "experimental": experimental, "id_version_clasificador": p.id_version_clasificador,
            "id_version_regresor": p.id_version_regresor, "id_ejecucion": p.id_ejecucion,
            "fecha_generacion": p.fecha_generacion})
    return resultado


def consulta_predicciones(horizonte, corte, ubigeo=None):
    consulta = select(Prediccion).where(Prediccion.horizonte == horizonte, Prediccion.id_semana_corte == corte)
    if ubigeo:
        consulta = consulta.where(Prediccion.ubigeo == ubigeo)
    return consulta.order_by(Prediccion.ubigeo)


def sin_prediccion(sesion, horizonte):
    """Motivo cuando no hay predicciones del horizonte (h=3 o aún sin publicar)."""
    if horizonte == 3:
        return MOTIVO_H3
    return "Aún no hay predicciones publicadas para este horizonte"


# --- series, tablero y mapa ------------------------------------------------------

def series(sesion, ubigeo, horizonte, desde, hasta):
    """Semanas continuas del calendario con observado y predicción (null si falta)."""
    d = distrito_existente(sesion, ubigeo)
    if hasta is None:
        ultima = sesion.scalar(select(func.max(SemanaEpidemiologica.fecha_inicio)).join(
            Prediccion, Prediccion.id_semana_objetivo == SemanaEpidemiologica.id_semana).where(
            Prediccion.ubigeo == ubigeo, Prediccion.horizonte == horizonte))
        ultima = ultima or sesion.scalar(select(func.max(SemanaEpidemiologica.fecha_inicio)).join(
            ObservacionSemanal, ObservacionSemanal.id_semana == SemanaEpidemiologica.id_semana))
        if ultima is None:
            raise ErrorAPI(409, "sin_datos", "No hay observaciones ni predicciones cargadas")
        hasta = ultima
    desde = desde or hasta - timedelta(weeks=25)
    if (hasta - desde).days > 7 * 520:
        raise ErrorAPI(422, "rango_invalido", "El rango de la serie no puede superar 10 años")
    cal = list(sesion.scalars(select(SemanaEpidemiologica).where(
        SemanaEpidemiologica.fecha_inicio >= desde, SemanaEpidemiologica.fecha_inicio <= hasta
    ).order_by(SemanaEpidemiologica.id_semana)))
    ids = [s.id_semana for s in cal]
    obs = {o.id_semana: o for o in sesion.scalars(select(ObservacionSemanal).where(
        ObservacionSemanal.ubigeo == ubigeo, ObservacionSemanal.id_semana.in_(ids)))} if ids else {}
    preds = list(sesion.scalars(select(Prediccion).where(
        Prediccion.ubigeo == ubigeo, Prediccion.horizonte == horizonte, Prediccion.id_semana_objetivo.in_(ids)))) if ids else []
    dtos = {dto["semana_objetivo"]["id_semana"]: dto for dto in prediccion_dtos(sesion, preds)}
    motivo = MOTIVO_H3 if horizonte == 3 else None
    return {**metadatos(sesion, motivo is None, motivo), "ubigeo": ubigeo, "distrito": d.nombre,
            "horizonte": horizonte, "desde": desde, "hasta": hasta,
            "elementos": [{"semana": semana_dto(s), "observado": s.id_semana in obs,
                           "casos_dengue": obs[s.id_semana].casos_dengue if s.id_semana in obs else None,
                           "brote": obs[s.id_semana].brote if s.id_semana in obs else None,
                           "prediccion": dtos.get(s.id_semana)} for s in cal]}


def predicciones_vigentes(sesion, horizonte):
    corte = corte_vigente(sesion, horizonte) if horizonte != 3 else None
    if corte is None:
        return None, []
    return corte, prediccion_dtos(sesion, list(sesion.scalars(consulta_predicciones(horizonte, corte))))


def tablero(sesion, horizonte):
    corte, dtos = predicciones_vigentes(sesion, horizonte)
    disponibles = [p for p in dtos if p["disponible"]]
    niveles = {n: sum(p["nivel_riesgo"] == n for p in disponibles) for n in NIVELES}
    total_distritos = sesion.scalar(select(func.count()).select_from(Distrito).where(Distrito.activo.is_(True)))
    activas = sesion.scalar(select(func.count()).select_from(Alerta).join(
        Prediccion, Prediccion.id_prediccion == Alerta.id_prediccion).where(
        Alerta.estado == "activa", Prediccion.horizonte == horizonte))
    ultima_obs = sesion.scalar(select(func.max(ObservacionSemanal.id_semana)))
    casos_obs = sesion.scalar(select(func.sum(ObservacionSemanal.casos_dengue)).where(
        ObservacionSemanal.id_semana == ultima_obs)) if ultima_obs else None
    completo = bool(dtos) and len(disponibles) == len(dtos)
    motivo = None if dtos else sin_prediccion(sesion, horizonte)
    return {**metadatos(sesion, bool(dtos), motivo), "horizonte": horizonte,
            "semana_corte": dtos[0]["semana_corte"] if dtos else None,
            "semana_objetivo": dtos[0]["semana_objetivo"] if dtos else None,
            "experimental": any(p["experimental"] for p in dtos),
            "distritos": total_distritos, "distritos_con_prediccion": len(disponibles),
            "niveles_riesgo": niveles, "alertas_activas": activas,
            "casos_estimados_region": {
                "disponible": completo, "valor": round(sum(p["casos_estimados"] or 0 for p in disponibles), 2) if completo else None,
                "motivo": None if completo else "Falta la magnitud de algún distrito; no se suma una región parcial"},
            "casos_observados_ultima_semana": {"disponible": casos_obs is not None, "valor": casos_obs,
                                               "motivo": None if casos_obs is not None else "No hay observaciones"},
            "nota": NOTA_EXPERIMENTAL if any(p["experimental"] for p in dtos) else
                    "Predicciones de una versión activa que cumple los umbrales"}


def mapa_riesgo(sesion, horizonte):
    """GeoJSON de centroides (Point): no hay polígonos en la referencia del proyecto."""
    corte, dtos = predicciones_vigentes(sesion, horizonte)
    por_ubigeo = {p["ubigeo"]: p for p in dtos}
    motivo_general = sin_prediccion(sesion, horizonte) if not dtos else None
    cortes = parametros.cortes_riesgo(sesion)
    features = []
    for d in sesion.scalars(select(Distrito).where(Distrito.activo.is_(True)).order_by(Distrito.ubigeo)):
        p = por_ubigeo.get(d.ubigeo)
        features.append({"type": "Feature", "id": d.ubigeo,
            "geometry": {"type": "Point", "coordinates": [d.longitud, d.latitud]},
            "properties": {"ubigeo": d.ubigeo, "distrito": d.nombre, "provincia": d.provincia.nombre,
                           "estado": p["estado"] if p else "no_disponible",
                           "nivel_riesgo": p["nivel_riesgo"] if p else None,
                           "nivel_riesgo_etiqueta": (p["nivel_riesgo_etiqueta"] if p else None) or "Sin datos",
                           "probabilidad_brote": p["probabilidad_brote"] if p else None,
                           "casos_estimados": p["casos_estimados"] if p else None,
                           "experimental": p["experimental"] if p else False,
                           "motivo": (p["motivo"] if p else motivo_general) or None}})
    leyenda = [{"nivel": "bajo", "etiqueta": "Bajo", "desde": 0.0, "hasta": cortes["medio"]},
               {"nivel": "medio", "etiqueta": "Medio", "desde": cortes["medio"], "hasta": cortes["alto"]},
               {"nivel": "alto", "etiqueta": "Alto", "desde": cortes["alto"], "hasta": cortes["muy_alto"]},
               {"nivel": "muy_alto", "etiqueta": "Muy alto", "desde": cortes["muy_alto"], "hasta": 1.0},
               {"nivel": None, "etiqueta": "Sin datos", "desde": None, "hasta": None}]
    return {**metadatos(sesion, bool(dtos), motivo_general), "type": "FeatureCollection", "horizonte": horizonte,
            "semana_corte": dtos[0]["semana_corte"] if dtos else None,
            "semana_objetivo": dtos[0]["semana_objetivo"] if dtos else None,
            "experimental": any(p["experimental"] for p in dtos), "leyenda": leyenda, "features": features}


# --- alertas -----------------------------------------------------------------------

def consulta_alertas(horizonte=None, ubigeo=None, nivel=None, estado=None):
    consulta = select(Alerta).join(Prediccion, Prediccion.id_prediccion == Alerta.id_prediccion)
    for condicion in (Prediccion.horizonte == horizonte if horizonte else None,
                      Alerta.ubigeo == ubigeo if ubigeo else None,
                      Alerta.nivel == nivel if nivel else None,
                      Alerta.estado == estado if estado else None):
        if condicion is not None:
            consulta = consulta.where(condicion)
    # Activas primero, luego muy_alto antes que alto y lo más reciente arriba.
    return consulta.order_by(Alerta.estado, Alerta.nivel.desc(), Alerta.fecha_generacion.desc(), Alerta.id_alerta.desc())


def alerta_dtos(sesion, filas):
    ids = {a.id_prediccion for a in filas}
    predicciones = list(sesion.scalars(select(Prediccion).where(Prediccion.id_prediccion.in_(ids)))) if ids else []
    preds = {p["id_prediccion"]: p for p in prediccion_dtos(sesion, predicciones)}
    return [{"id_alerta": a.id_alerta, "ubigeo": a.ubigeo, "distrito": preds[a.id_prediccion]["distrito"],
             "horizonte": preds[a.id_prediccion]["horizonte"], "nivel": a.nivel,
             "nivel_etiqueta": ETIQUETAS[a.nivel], "estado": a.estado, "cambio": a.cambio,
             "fecha_generacion": a.fecha_generacion, "fecha_retiro": a.fecha_retiro, "motivo": a.motivo,
             "experimental": preds[a.id_prediccion]["experimental"], "prediccion": preds[a.id_prediccion]}
            for a in filas]


# --- modelos -----------------------------------------------------------------------

def modelo_existente(sesion, identificador):
    v = sesion.get(VersionModelo, identificador)
    if v is None:
        raise ErrorAPI(404, "modelo_no_encontrado", "La versión de modelo no existe")
    return v


def modelo_dto(v, detalle=False):
    dto = {"id_version": v.id_version, "codigo": v.codigo, "tarea": v.tarea, "horizonte": v.horizonte,
           "algoritmo": v.algoritmo, "estado": v.estado, "cumple_umbrales": v.cumple_umbrales,
           "experimental": not v.cumple_umbrales, "umbral_probabilidad": v.umbral_probabilidad,
           "mlflow_run_id": v.mlflow_run_id, "fecha_registro": v.fecha_registro,
           "fecha_activacion": v.fecha_activacion}
    if detalle:
        dto.update(variables=v.variables, hiperparametros=v.hiperparametros, metricas=v.metricas,
                   ruta_artefacto=v.ruta_artefacto, sha256_artefacto=v.sha256_artefacto,
                   sha256_dataset=v.sha256_dataset, reproducibilidad=v.reproducibilidad)
    return dto


def modelos_en_uso(sesion, horizonte, servir_no_validadas):
    horizontes = [horizonte] if horizonte else sorted(set(sesion.scalars(select(VersionModelo.horizonte))))
    elementos = []
    for h in horizontes:
        versiones, _ = seleccionar_versiones(sesion, h, servir_no_validadas)
        for tarea in TAREAS:
            if tarea in versiones:
                v = versiones[tarea]
                elementos.append({**modelo_dto(v), "seleccion": "activa" if v.estado == "activa" else "experimental"})
    motivo = None if elementos else (MOTIVO_H3 if horizonte == 3 else "No hay versiones activas ni selección experimental utilizable")
    experimental = any(e["experimental"] for e in elementos)
    return {**metadatos(sesion, bool(elementos), motivo), "elementos": elementos,
            "nota": NOTA_EXPERIMENTAL if experimental else "Versiones activas que cumplen los umbrales de aceptación"}


def variables(sesion, identificador):
    modelo_existente(sesion, identificador)
    filas = list(sesion.scalars(select(ImportanciaVariable).where(
        ImportanciaVariable.id_version == identificador).order_by(ImportanciaVariable.rango)))
    return {**metadatos(sesion, bool(filas), None if filas else "La versión no tiene importancias guardadas"),
            "id_version": identificador,
            "elementos": [{"variable": f.variable, "importancia": f.importancia, "rango": f.rango} for f in filas],
            "nota": "Importancia gain del booster; no implica causalidad"}


# --- salud -----------------------------------------------------------------------

def salud(sesion, version_api):
    ultima = sesion.scalar(select(Ejecucion).where(Ejecucion.estado == "exitosa")
                           .order_by(Ejecucion.id_ejecucion.desc()).limit(1))
    return {**metadatos(sesion), "estado": "ok", "conexion_bd": True, "version_api": version_api,
            "ultima_ejecucion": None if ultima is None else {
                "id_ejecucion": ultima.id_ejecucion, "tipo": ultima.tipo, "estado": ultima.estado,
                "id_semana_corte": ultima.id_semana_corte, "fin": ultima.fin}}
