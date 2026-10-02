"""Observaciones, predicciones y series temporales (HU0010, HU0011, HU0013)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from src.api import consultas as q
from src.api.dependencias import (Horizonte, PaginaNumero, Sesion, TamanoPagina, Ubigeo,
                                  lectura, validar_rango)
from src.api.esquemas import ObservacionRespuesta, Pagina, PrediccionRespuesta, SeriesRespuesta

router = APIRouter(tags=["Datos semanales"])
Desde = Annotated[date | None, Query(description="Inicio inclusivo (fecha de inicio de semana), AAAA-MM-DD")]
Hasta = Annotated[date | None, Query(description="Fin inclusivo (fecha de inicio de semana), AAAA-MM-DD")]
Corte = Annotated[int | None, Query(ge=201701, le=209953,
                                    description="Semana de corte anio*100+semana; por defecto, el corte vigente")]


@router.get("/observaciones", response_model=Pagina[ObservacionRespuesta],
            summary="Consultar casos y clima observados (extensión)")
def observaciones(request: Request, response: Response, sesion: Sesion,
                  ubigeo: Ubigeo | None = None, desde: Desde = None, hasta: Hasta = None,
                  pagina: PaginaNumero = 1, tamano_pagina: TamanoPagina = 50):
    """Los ceros se conservan; una ausencia es null y su cobertura se informa."""
    validar_rango(desde, hasta)
    if ubigeo:
        q.distrito_existente(sesion, ubigeo)
    return lectura(request, response, sesion, lambda: q.paginar(
        sesion, q.consulta_observaciones(ubigeo, desde, hasta), pagina, tamano_pagina,
        lambda filas: q.observacion_dtos(sesion, filas)))


@router.get("/predicciones", response_model=Pagina[PrediccionRespuesta],
            summary="Predicciones por distrito para un horizonte y semana de corte (HU0010, HU0011)")
def predicciones(request: Request, response: Response, sesion: Sesion, horizonte: Horizonte,
                 ubigeo: Ubigeo | None = None, corte: Corte = None,
                 pagina: PaginaNumero = 1, tamano_pagina: TamanoPagina = 65):
    """Sin ``corte`` devuelve el corte vigente. h=3 responde disponible=false (sin modelo para h=3)."""
    if ubigeo:
        q.distrito_existente(sesion, ubigeo)

    def construir():
        elegido = corte or (q.corte_vigente(sesion, horizonte) if horizonte != 3 else None)
        if elegido is None:
            meta = q.metadatos(sesion, False, q.sin_prediccion(sesion, horizonte))
            return {**meta, "elementos": [], "total": 0, "pagina": pagina, "tamano_pagina": tamano_pagina}
        resultado = q.paginar(sesion, q.consulta_predicciones(horizonte, elegido, ubigeo), pagina, tamano_pagina,
                              lambda filas: q.prediccion_dtos(sesion, filas))
        if resultado["total"] == 0:
            resultado.update(disponible=False, motivo="No hay predicciones para ese corte y horizonte")
        return resultado
    return lectura(request, response, sesion, construir)


@router.get("/series/{ubigeo}", response_model=SeriesRespuesta,
            summary="Serie semanal de casos observados y predicciones del distrito (HU0013)")
def series(ubigeo: Ubigeo, request: Request, response: Response, sesion: Sesion,
           horizonte: Horizonte, desde: Desde = None, hasta: Hasta = None):
    """Todas las semanas del intervalo (por defecto 26 hasta la última predicción), con null en los huecos."""
    validar_rango(desde, hasta)
    return lectura(request, response, sesion, lambda: q.series(sesion, ubigeo, horizonte, desde, hasta))
