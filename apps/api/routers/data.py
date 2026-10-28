"""Observations, predictions and time series (HU0010, HU0011, HU0013)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from apps.api import queries as q
from apps.api.dependencies import (Horizon, PageNumber, DbSession, PageSize, Ubigeo,
                                  cached_read, validate_range)
from apps.api.schemas import ObservacionRespuesta, Pagina, PrediccionRespuesta, SeriesRespuesta

router = APIRouter(tags=["Datos semanales"])
FromDate = Annotated[date | None, Query(description="Inicio inclusivo (fecha de inicio de semana), AAAA-MM-DD")]
ToDate = Annotated[date | None, Query(description="Fin inclusivo (fecha de inicio de semana), AAAA-MM-DD")]
Cutoff = Annotated[int | None, Query(ge=201701, le=209953,
                                    description="Semana de corte anio*100+semana; por defecto, el corte vigente")]


@router.get("/observaciones", response_model=Pagina[ObservacionRespuesta],
            summary="Consultar casos y clima observados (extensión)")
def observaciones(request: Request, response: Response, sesion: DbSession,
                  ubigeo: Ubigeo | None = None, desde: FromDate = None, hasta: ToDate = None,
                  pagina: PageNumber = 1, tamano_pagina: PageSize = 50):
    """Los ceros se conservan; una ausencia es null y su cobertura se informa."""
    validate_range(desde, hasta)
    if ubigeo:
        q.existing_district(sesion, ubigeo)
    return cached_read(request, response, sesion, lambda: q.paginate(
        sesion, q.observations_query(ubigeo, desde, hasta), pagina, tamano_pagina,
        lambda filas: q.observation_dtos(sesion, filas)))


@router.get("/predicciones", response_model=Pagina[PrediccionRespuesta],
            summary="Predicciones por distrito para un horizonte y semana de corte (HU0010, HU0011)")
def predicciones(request: Request, response: Response, sesion: DbSession, horizonte: Horizon,
                 ubigeo: Ubigeo | None = None, corte: Cutoff = None,
                 pagina: PageNumber = 1, tamano_pagina: PageSize = 65):
    """Sin ``corte`` devuelve el corte vigente. h=3 responde disponible=false (sin modelo para h=3)."""
    if ubigeo:
        q.existing_district(sesion, ubigeo)

    def build():
        chosen = corte or (q.current_cutoff(sesion, horizonte) if horizonte != 3 else None)
        if chosen is None:
            meta = q.metadata(sesion, False, q.no_prediction_reason(sesion, horizonte))
            return {**meta, "elementos": [], "total": 0, "pagina": pagina, "tamano_pagina": tamano_pagina}
        result = q.paginate(sesion, q.predictions_query(horizonte, chosen, ubigeo), pagina, tamano_pagina,
                              lambda filas: q.prediction_dtos(sesion, filas))
        if result["total"] == 0:
            result.update(disponible=False, motivo="No hay predicciones para ese corte y horizonte")
        return result
    return cached_read(request, response, sesion, build)


@router.get("/series/{ubigeo}", response_model=SeriesRespuesta,
            summary="Serie semanal de casos observados y predicciones del distrito (HU0013)")
def series(ubigeo: Ubigeo, request: Request, response: Response, sesion: DbSession,
           horizonte: Horizon, desde: FromDate = None, hasta: ToDate = None):
    """Todas las semanas del intervalo (por defecto 26 hasta la última predicción), con null en los huecos."""
    validate_range(desde, hasta)
    return cached_read(request, response, sesion, lambda: q.series(sesion, ubigeo, horizonte, desde, hasta))
