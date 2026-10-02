"""Inferencia por semana de corte desde la BD, alertas e importación de predicciones OOS.

El vector de características se reconstruye en memoria desde
``observacion_semanal`` y ``distrito.poblacion_censo_2017`` con las mismas
funciones del modelado (``construir_filas_futuras``); no se persiste.
"""

from time import perf_counter

import numpy as np
import pandas as pd
from sqlalchemy import select

from src.db.modelos import (Alerta, Distrito, Ejecucion, ObservacionSemanal, Prediccion,
                            SemanaEpidemiologica, VersionModelo, ahora_utc)
from src.db.sesion import upsert
from src.modeling.inferencia_futura import construir_filas_futuras
from src.modeling.sociodemografia import DIRECTAS
from src.serving import parametros
from src.serving.artefactos import predecir_con_version
from src.serving.riesgo import NIVELES_ALERTA, cambio_alerta, nivel_riesgo

TAREAS = ("clasificacion", "regresion")
BLOQUES_OOS = ("temporada_2022", "temporada_2023", "temporada_2024", "calendario_2025")
MOTIVO_H3 = "sin modelo para h=3"


class InferenciaNoDisponible(ValueError):
    """La solicitud no se puede atender con los datos o modelos de la BD (HTTP 409)."""


# --- calendario y datos ------------------------------------------------------

def semana(sesion, id_semana):
    fila = sesion.get(SemanaEpidemiologica, id_semana)
    if fila is None:
        raise InferenciaNoDisponible(f"La semana {id_semana} no está en el calendario epidemiológico")
    return fila


def semana_objetivo(sesion, corte, horizonte):
    inicio = corte.fecha_inicio + pd.Timedelta(weeks=horizonte).to_pytimedelta()
    fila = sesion.scalar(select(SemanaEpidemiologica).where(SemanaEpidemiologica.fecha_inicio == inicio))
    if fila is None:
        raise InferenciaNoDisponible("La semana objetivo no está en el calendario; recargue los datos")
    return fila


def ultima_semana_observada(sesion):
    valor = sesion.scalar(select(ObservacionSemanal.id_semana).order_by(ObservacionSemanal.id_semana.desc()).limit(1))
    if valor is None:
        raise InferenciaNoDisponible("No hay observaciones cargadas")
    return valor


def panel_desde_bd(sesion, hasta):
    """Panel mínimo (casos por distrito y semana) cerrado a la fecha ``hasta``."""
    filas = sesion.execute(select(
        ObservacionSemanal.ubigeo, SemanaEpidemiologica.anio, SemanaEpidemiologica.semana,
        SemanaEpidemiologica.fecha_inicio, ObservacionSemanal.casos_dengue
    ).join(SemanaEpidemiologica, SemanaEpidemiologica.id_semana == ObservacionSemanal.id_semana
    ).where(SemanaEpidemiologica.fecha_fin <= hasta)).all()
    panel = pd.DataFrame(filas, columns=["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"])
    panel["ubigeo"] = panel.ubigeo.astype("string")
    panel["semana_inicio"] = pd.to_datetime(panel.semana_inicio)
    panel["casos_Dengue"] = panel.casos_Dengue.astype(float)
    return panel.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)


def referencia_desde_bd(sesion):
    """Referencia censal 2017 desde ``distrito``.

    ``construir_sociodemografia`` exige además tres fracciones de 2017; los
    modelos de servicio solo usan ``log_poblacion_censo_2017``, así que esas
    fracciones se completan con 0 y no entran al vector (se descartan).
    """
    filas = sesion.execute(select(Distrito.ubigeo, Distrito.poblacion_censo_2017).where(
        Distrito.poblacion_censo_2017.is_not(None))).all()
    referencia = pd.DataFrame(filas, columns=["ubigeo", "poblacion"])
    referencia["ubigeo"] = referencia.ubigeo.astype("string")
    for columna in DIRECTAS:
        referencia[columna] = 0.0
    return referencia


def vectores_desde_bd(sesion, horizonte, id_semana_corte, columnas):
    """Vectores del objetivo corte+h, sin escribir nada. Devuelve (filas, motivos)."""
    corte = semana(sesion, id_semana_corte)
    panel = panel_desde_bd(sesion, corte.fecha_fin)
    if panel.empty:
        raise InferenciaNoDisponible("No hay observaciones cerradas al corte solicitado")
    try:
        filas, motivos = construir_filas_futuras(panel, horizonte, columnas=columnas,
                                                 fecha_corte=pd.Timestamp(corte.fecha_fin),
                                                 referencia=referencia_desde_bd(sesion))
    except ValueError as error:
        raise InferenciaNoDisponible(str(error)) from error
    return filas, {m["ubigeo"]: m["motivo"] for m in motivos}


# --- selección de versiones ----------------------------------------------------

def seleccionar_versiones(sesion, horizonte, servir_no_validadas):
    """Versión activa por tarea; si no hay, la selección experimental (desviación temporal).

    Devuelve ({tarea: VersionModelo}, motivo); el diccionario está incompleto
    cuando no hay versión utilizable para alguna tarea.
    """
    versiones = {v.tarea: v for v in sesion.scalars(select(VersionModelo).where(
        VersionModelo.horizonte == horizonte, VersionModelo.estado == "activa"))}
    faltan = [t for t in TAREAS if t not in versiones]
    if faltan and servir_no_validadas:
        codigos = parametros.seleccion_experimental(sesion).get(horizonte, {})
        for tarea in faltan:
            codigo = codigos.get(tarea)
            version = codigo and sesion.scalar(select(VersionModelo).where(VersionModelo.codigo == codigo))
            if version is not None and version.tarea == tarea and version.horizonte == horizonte:
                versiones[tarea] = version
    if all(t in versiones for t in TAREAS):
        return versiones, None
    if not servir_no_validadas:
        return versiones, "Predicción no disponible: no hay un modelo activo que cumpla los umbrales"
    return versiones, f"Predicción no disponible: no hay versiones utilizables para h={horizonte}"


def es_experimental(versiones):
    return any(not v.cumple_umbrales for v in versiones.values())


# --- inferencia -----------------------------------------------------------------

def _registro(ubigeo, corte, objetivo, horizonte, ejecucion, versiones, probabilidad, casos, motivo, cortes):
    disponible = probabilidad is not None
    probabilidad = round(float(probabilidad), 4) if disponible else None  # numeric(5,4) del DDL
    return {"ubigeo": ubigeo, "id_semana_corte": corte, "id_semana_objetivo": objetivo,
            "horizonte": horizonte, "probabilidad_brote": probabilidad,
            "nivel_riesgo": nivel_riesgo(probabilidad, cortes) if disponible else None,
            "casos_estimados": round(float(casos), 2) if disponible and casos is not None else None,
            "estado": "disponible" if disponible else "no_disponible",
            "motivo_no_disponible": None if disponible else motivo,
            "id_version_clasificador": versiones["clasificacion"].id_version if "clasificacion" in versiones else None,
            "id_version_regresor": versiones["regresion"].id_version if "regresion" in versiones else None,
            "id_ejecucion": ejecucion, "fecha_generacion": ahora_utc()}


def inferir(sesion, horizonte, id_semana_corte=None, *, almacenamiento, servir_no_validadas, origen="api"):
    """Genera (UPSERT) la predicción de cada distrito para un corte y horizonte.

    Crea una ``ejecucion`` de tipo ``inferencia``; el llamador confirma la
    transacción. Sin versión utilizable, las filas quedan ``no_disponible``.
    """
    inicio = perf_counter()
    if horizonte == 3:
        raise InferenciaNoDisponible(MOTIVO_H3)
    if horizonte not in (2, 4):
        raise ValueError("horizonte debe ser 2, 3 o 4")
    id_semana_corte = id_semana_corte or ultima_semana_observada(sesion)
    corte = semana(sesion, id_semana_corte)
    if sesion.scalar(select(ObservacionSemanal.id_semana).where(
            ObservacionSemanal.id_semana == id_semana_corte).limit(1)) is None:
        raise InferenciaNoDisponible(f"No hay observaciones para la semana de corte {id_semana_corte}")
    objetivo = semana_objetivo(sesion, corte, horizonte)
    cortes = parametros.cortes_riesgo(sesion)
    versiones, motivo = seleccionar_versiones(sesion, horizonte, servir_no_validadas)
    ejecucion = Ejecucion(tipo="inferencia", estado="en_curso", id_semana_corte=id_semana_corte,
                          detalle={"origen": origen, "horizonte": horizonte})
    sesion.add(ejecucion)
    sesion.flush()
    distritos = list(sesion.scalars(select(Distrito.ubigeo).where(Distrito.activo.is_(True)).order_by(Distrito.ubigeo)))
    probabilidades, casos, motivos = {}, {}, {}
    if motivo is None:
        columnas = sorted({c for v in versiones.values() for c in v.variables})
        filas, motivos = vectores_desde_bd(sesion, horizonte, id_semana_corte, columnas)
        if not filas.empty:
            p = predecir_con_version(versiones["clasificacion"], filas, almacenamiento)
            c = predecir_con_version(versiones["regresion"], filas, almacenamiento)
            probabilidades = dict(zip(filas.ubigeo, map(float, p)))
            casos = dict(zip(filas.ubigeo, map(float, c)))
    registros = [_registro(u, id_semana_corte, objetivo.id_semana, horizonte, ejecucion.id_ejecucion, versiones,
                           probabilidades.get(u), casos.get(u),
                           motivo or motivos.get(u, "No hay vector de características para el distrito"), cortes)
                 for u in distritos]
    upsert(sesion, Prediccion.__table__, registros, ["ubigeo", "id_semana_corte", "horizonte"])
    sesion.flush()
    alertas = actualizar_alertas(sesion, horizonte, id_semana_corte)
    experimental = motivo is None and es_experimental(versiones)
    disponibles = sum(r["estado"] == "disponible" for r in registros)
    ejecucion.estado = "exitosa"
    ejecucion.fin = ahora_utc()
    ejecucion.detalle = {
        "origen": origen, "horizonte": horizonte, "id_semana_corte": id_semana_corte,
        "id_semana_objetivo": objetivo.id_semana, "experimental": experimental,
        "seleccion": "experimental" if experimental else ("activa" if motivo is None else None),
        "versiones": {t: v.codigo for t, v in versiones.items()}, "motivo": motivo,
        "predicciones": len(registros), "disponibles": disponibles,
        "no_disponibles": len(registros) - disponibles, "alertas": alertas,
        "duracion_segundos": round(perf_counter() - inicio, 3)}
    sesion.flush()
    return {"id_ejecucion": ejecucion.id_ejecucion, **ejecucion.detalle}


def actualizar_alertas(sesion, horizonte, id_semana_corte):
    """Una alerta activa por distrito y horizonte; ``cambio`` respecto del corte anterior."""
    ahora = ahora_utc()
    actuales = list(sesion.scalars(select(Prediccion).where(
        Prediccion.horizonte == horizonte, Prediccion.id_semana_corte == id_semana_corte)))
    anteriores = {}
    for alerta, corte in sesion.execute(select(Alerta, Prediccion.id_semana_corte).join(
            Prediccion, Prediccion.id_prediccion == Alerta.id_prediccion).where(
            Prediccion.horizonte == horizonte, Prediccion.id_semana_corte < id_semana_corte,
            Alerta.estado == "activa").order_by(Prediccion.id_semana_corte)):
        anteriores[alerta.ubigeo] = alerta  # queda la del corte más reciente
    propias = {a.id_prediccion: a for a in sesion.scalars(select(Alerta).where(
        Alerta.id_prediccion.in_([p.id_prediccion for p in actuales])))} if actuales else {}
    conteo = {"nuevas_o_actualizadas": 0, "retiradas": 0}

    def retirar(alerta, motivo):
        if alerta.estado == "activa":
            alerta.estado, alerta.fecha_retiro, alerta.motivo = "retirada", ahora, motivo
            conteo["retiradas"] += 1

    for p in actuales:
        anterior = anteriores.get(p.ubigeo)
        propia = propias.get(p.id_prediccion)
        if p.estado == "disponible" and p.nivel_riesgo in NIVELES_ALERTA:
            cambio = cambio_alerta(anterior.nivel if anterior else None, p.nivel_riesgo)
            if propia is None:
                sesion.add(Alerta(id_prediccion=p.id_prediccion, ubigeo=p.ubigeo, nivel=p.nivel_riesgo,
                                  estado="activa", cambio=cambio, fecha_generacion=ahora))
            else:
                propia.nivel, propia.cambio, propia.estado = p.nivel_riesgo, cambio, "activa"
                propia.fecha_generacion, propia.fecha_retiro, propia.motivo = ahora, None, None
            conteo["nuevas_o_actualizadas"] += 1
            if anterior is not None:
                retirar(anterior, f"Sustituida por la alerta del corte {id_semana_corte}")
        else:
            if propia is not None:
                retirar(propia, "La predicción recalculada ya no alcanza nivel alto")
            if anterior is not None:
                retirar(anterior, f"El riesgo del corte {id_semana_corte} ya no alcanza nivel alto")
    sesion.flush()
    return conteo


# --- predicciones OOS (cortes pasados) --------------------------------------

def importar_oos(sesion, protocolo, horizontes, cfg, versiones_servicio):
    """Guarda las predicciones fuera de muestra del protocolo como cortes pasados.

    Una ``ejecucion`` de tipo ``inferencia`` por horizonte y bloque, con el
    bloque y su origen en ``detalle``; ``id_version_*`` en NULL porque esos
    boosters no se conservaron. No generan alertas: son históricas.
    """
    cortes = parametros.cortes_riesgo(sesion)
    calendario = pd.DataFrame(sesion.execute(select(
        SemanaEpidemiologica.id_semana, SemanaEpidemiologica.fecha_fin)).all(), columns=["id_semana", "fecha_fin"])
    corte_por_fecha = dict(zip(pd.to_datetime(calendario.fecha_fin), calendario.id_semana))
    fin_por_id = dict(zip(calendario.id_semana, pd.to_datetime(calendario.fecha_fin)))
    resumen = []
    for h in horizontes:
        experimental = not all(versiones_servicio[h, t].cumple_umbrales for t in TAREAS)
        # cargar_protocolo ya verificó la cobertura de cada bloque contra gold.
        presentes = set(protocolo.predicciones.loc[protocolo.predicciones.horizonte.eq(h), "bloque"])
        for bloque in [b for b in BLOQUES_OOS if b in presentes]:
            base = protocolo.predicciones.loc[protocolo.predicciones.horizonte.eq(h) & protocolo.predicciones.bloque.eq(bloque)]
            cls = base.loc[base.variante.eq(cfg.variantes["clasificacion"])].set_index(["ubigeo", "anio", "semana"]).sort_index()
            reg = base.loc[base.variante.eq(cfg.variantes["regresion"])].set_index(["ubigeo", "anio", "semana"]).sort_index()
            if cls.empty or not cls.index.equals(reg.index):
                raise ValueError(f"Clasificación y regresión OOS no comparten semanas en {bloque} h={h}")
            ejecucion = Ejecucion(tipo="inferencia", estado="en_curso", detalle={"origen": "oos_protocolo"})
            sesion.add(ejecucion)
            sesion.flush()
            registros = []
            for (ubigeo, anio, semana_obj), fila in cls.iterrows():
                corte = corte_por_fecha.get(pd.Timestamp(fila.origen_cierre))
                if corte is None:
                    raise ValueError("El origen OOS no corresponde a un cierre del calendario")
                probabilidad = float(fila.probabilidad_brote)
                casos = float(reg.loc[(ubigeo, anio, semana_obj), "casos_predichos"])
                if not np.isfinite([probabilidad, casos]).all() or casos < 0:
                    raise ValueError("No se importan predicciones OOS no finitas o negativas")
                objetivo = int(anio) * 100 + int(semana_obj)
                if fin_por_id.get(objetivo) != pd.Timestamp(fila.origen_cierre) + pd.Timedelta(weeks=h):
                    raise ValueError("La predicción OOS no respeta la distancia corte-objetivo h")
                registros.append(_registro(ubigeo, int(corte), objetivo, h,
                                           ejecucion.id_ejecucion, {}, probabilidad, casos, None, cortes))
            upsert(sesion, Prediccion.__table__, registros, ["ubigeo", "id_semana_corte", "horizonte"])
            ejecucion.estado, ejecucion.fin = "exitosa", ahora_utc()
            ejecucion.id_semana_corte = max(r["id_semana_corte"] for r in registros)
            ejecucion.detalle = {"origen": "oos_protocolo", "horizonte": h, "bloque": bloque,
                                 "experimental": experimental, "predicciones": len(registros),
                                 "variantes": dict(cfg.variantes),
                                 "sha256_protocolo": protocolo.hashes,
                                 "nota": "Predicciones fuera de muestra del protocolo temporal; sin booster conservado"}
            resumen.append({"horizonte": h, "bloque": bloque, "predicciones": len(registros),
                            "id_ejecucion": ejecucion.id_ejecucion})
    sesion.flush()
    return resumen
