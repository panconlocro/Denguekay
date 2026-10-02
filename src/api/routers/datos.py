"""Observaciones, predicciones y series temporales con faltantes explícitos."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select

from src.api import consultas as q
from src.api.dependencias import (Horizonte, PaginaNumero, Sesion, TamanoPagina, Ubigeo,
    exigir_clave, lectura, validar_rango, validar_semana)
from src.api.errores import ErrorAPI
from src.api.esquemas import (ObservacionRespuesta, Pagina, PrediccionRespuesta,
                             ReevaluacionRespuesta, SeriesRespuesta)
from src.db.modelos import ObservacionSemanal
from src.serving.reevaluacion import ReevaluacionNoDisponible, reevaluar

router = APIRouter(tags=["Datos semanales"])
Desde = Annotated[date | None, Query(description="Inicio inclusivo del periodo, AAAA-MM-DD")]
Hasta = Annotated[date | None, Query(description="Fin inclusivo del periodo, AAAA-MM-DD")]
Semana = Annotated[date | None, Query(description="Domingo de la semana objetivo, AAAA-MM-DD; no usa numeración ISO")]


@router.get("/observaciones", response_model=Pagina[ObservacionRespuesta], summary="Consultar casos observados por distrito y periodo")
def observaciones(request: Request, response: Response, sesion: Sesion,
                  ubigeo: Ubigeo | None = None, desde: Desde = None, hasta: Hasta = None,
                  pagina: PaginaNumero = 1, tamano_pagina: TamanoPagina = 50):
    """Los ceros epidemiológicos se conservan; una ausencia es null con motivo."""
    validar_rango(desde, hasta)
    if ubigeo:
        q.distrito_existente(sesion, ubigeo)
    def construir():
        consulta = select(ObservacionSemanal)
        for condicion in (ObservacionSemanal.ubigeo == ubigeo if ubigeo else None,
                          ObservacionSemanal.semana_inicio >= desde if desde else None,
                          ObservacionSemanal.semana_inicio <= hasta if hasta else None):
            if condicion is not None:
                consulta = consulta.where(condicion)
        meta = q.metadatos(sesion)
        return q.paginar(sesion, consulta.order_by(ObservacionSemanal.semana_inicio, ObservacionSemanal.ubigeo),
            pagina, tamano_pagina, lambda o: q.observacion_dto(o, q.distrito_existente(sesion, o.ubigeo), meta))
    return lectura(request, response, sesion, construir)


@router.get("/predicciones", response_model=Pagina[PrediccionRespuesta], summary="Consultar última publicación vigente de un horizonte")
def predicciones(request: Request, response: Response, sesion: Sesion, horizonte: Horizonte,
                 ubigeo: Ubigeo | None = None, semana: Semana = None,
                 pagina: PaginaNumero = 1, tamano_pagina: TamanoPagina = 65):
    """Vigente significa respecto del corte de datos. No recupera un pronóstico anterior como actual.

    Probabilidad, riesgo y magnitud proceden de la BD; la política puede bloquear
    versiones experimentales. Los resultados OOS se consultan mediante series.
    """
    validar_semana(semana)
    if ubigeo:
        q.distrito_existente(sesion, ubigeo)
    def construir():
        consulta, fuente = q.consulta_predicciones(sesion, horizonte, ubigeo, semana)
        meta = q.metadatos_predicciones(sesion, fuente)
        resultado = q.paginar(sesion, consulta, pagina, tamano_pagina,
            lambda p: q.prediccion_dto(p, q.distrito_existente(sesion, p.ubigeo),
                request.app.state.cfg, meta, fuente))
        resultado.update(fecha_corte_datos=meta["fecha_corte_datos"],
                         fecha_actualizacion=meta["fecha_actualizacion"])
        if resultado["elementos"] and not any(p["disponible"] for p in resultado["elementos"]):
            resultado.update(disponible=False, motivo=resultado["elementos"][0]["motivo"])
        return resultado
    return lectura(request, response, sesion, construir)


@router.get("/series/{ubigeo}", response_model=SeriesRespuesta, summary="Comparar casos observados y pronósticos fuera de muestra")
def series(ubigeo: Ubigeo, request: Request, response: Response, sesion: Sesion,
           horizonte: Horizonte, desde: Desde = None, hasta: Hasta = None):
    """Genera todas las semanas del intervalo, con null para huecos; conserva el calendario MMWR."""
    validar_rango(desde, hasta)
    return lectura(request, response, sesion, lambda: q.series(sesion, ubigeo, horizonte,
        desde, hasta, request.app.state.cfg))


@router.post("/predicciones/recalcular", response_model=ReevaluacionRespuesta,
             dependencies=[Depends(exigir_clave)], summary="Reevaluar vectores vigentes usando los boosters de la BD")
def recalcular(request: Request, sesion: Sesion, horizonte: Horizonte):
    """Exige X-API-Key. Crea una ejecución nueva y conserva predicciones previas.

    No entrena, no cambia el corte de datos y no reemplaza los resultados OOS.
    Un esquema incompatible o un ajuste posterior al origen impide la publicación.
    """
    return publicar_reevaluacion(request, sesion, horizonte)


def publicar_reevaluacion(request, sesion, horizonte, candidata=None):
    """Confirma conjuntamente la activación, predicciones y retiro de alertas."""
    try:
        resultado = reevaluar(sesion, horizonte, request.app.state.cfg, candidata)
        sesion.commit()
    except ReevaluacionNoDisponible as error:
        sesion.rollback()
        raise ErrorAPI(409, "reevaluacion_no_disponible", str(error)) from error
    request.app.state.cache.limpiar()
    request.app.openapi_schema = None
    return resultado
