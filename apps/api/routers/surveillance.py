"""Tablero, mapa de riesgo y alertas (HU0012, HU0014, HU0015)."""

from typing import Literal

from fastapi import APIRouter, Request, Response

from apps.api import queries as q
from apps.api.dependencies import Horizonte, Identificador, PaginaNumero, Sesion, TamanoPagina, Ubigeo, lectura
from apps.api.errors import ErrorAPI
from apps.api.schemas import AlertaRespuesta, MapaRiesgoRespuesta, Pagina, TableroRespuesta
from denguekay.db.models import Alert

router = APIRouter(tags=["Vigilancia"])


@router.get("/tablero/resumen", response_model=TableroRespuesta, summary="Resumen del corte vigente (HU0012)")
def tablero(request: Request, response: Response, sesion: Sesion, horizonte: Horizonte):
    """Niveles de riesgo, alertas activas y casos; la suma regional es null si falta algún distrito."""
    return lectura(request, response, sesion, lambda: q.tablero(sesion, horizonte))


@router.get("/mapa-riesgo", response_model=MapaRiesgoRespuesta, summary="Mapa de riesgo GeoJSON (HU0014)")
def mapa_riesgo(request: Request, response: Response, sesion: Sesion, horizonte: Horizonte):
    """FeatureCollection con un Point (centroide) por distrito y su nivel de riesgo o Sin datos."""
    return lectura(request, response, sesion, lambda: q.mapa_riesgo(sesion, horizonte))


@router.get("/alertas", response_model=Pagina[AlertaRespuesta], summary="Listar alertas (HU0015)")
def alertas(request: Request, response: Response, sesion: Sesion,
            horizonte: Horizonte | None = None, ubigeo: Ubigeo | None = None,
            nivel: Literal["alto", "muy_alto"] | None = None,
            estado: Literal["activa", "retirada"] | None = None,
            pagina: PaginaNumero = 1, tamano_pagina: TamanoPagina = 50):
    """Filtros por horizonte, distrito y nivel (Tabla 2); ``estado`` es un filtro extra."""
    if ubigeo:
        q.distrito_existente(sesion, ubigeo)
    return lectura(request, response, sesion, lambda: q.paginar(sesion,
        q.consulta_alertas(horizonte, ubigeo, nivel, estado), pagina, tamano_pagina,
        lambda filas: q.alerta_dtos(sesion, filas)))


@router.get("/alertas/{identificador}", response_model=AlertaRespuesta, summary="Consultar una alerta (extensión)")
def alerta(identificador: Identificador, request: Request, response: Response, sesion: Sesion):
    """Incluye la predicción que la sustenta; conserva estado retirado y motivo."""
    def construir():
        a = sesion.get(Alert, identificador)
        if a is None:
            raise ErrorAPI(404, "alerta_no_encontrada", "La alerta no existe")
        return q.alerta_dtos(sesion, [a])[0]
    return lectura(request, response, sesion, construir)
