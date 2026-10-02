"""Mapa, indicadores consolidados y alertas con trazabilidad."""

from typing import Literal

from fastapi import APIRouter, Request, Response

from src.api import consultas as q
from src.api.dependencias import Horizonte, Identificador, PaginaNumero, Sesion, TamanoPagina, Ubigeo, lectura
from src.api.errores import ErrorAPI
from src.api.esquemas import AlertaRespuesta, MapaRespuesta, Pagina, TableroRespuesta
from src.db.modelos import Alerta

router = APIRouter(tags=["Vigilancia"])


@router.get("/mapa", response_model=MapaRespuesta, summary="Mostrar todos los distritos con riesgo o Sin datos")
def mapa(request: Request, response: Response, sesion: Sesion, horizonte: Horizonte):
    """Incluye leyenda configurable, corte epidemiológico y motivos de ausencia."""
    return lectura(request, response, sesion, lambda: q.mapa(sesion, horizonte, request.app.state.cfg))


@router.get("/tablero", response_model=TableroRespuesta, summary="Consultar indicadores del último periodo pronosticado")
def tablero(request: Request, response: Response, sesion: Sesion, horizonte: Horizonte):
    """El total regional es null cuando falta magnitud para algún distrito; muestra cobertura real."""
    return lectura(request, response, sesion, lambda: q.tablero(sesion, horizonte, request.app.state.cfg))


@router.get("/alertas", response_model=Pagina[AlertaRespuesta], summary="Listar alertas por nivel de riesgo descendente")
def alertas(request: Request, response: Response, sesion: Sesion,
            horizonte: Horizonte | None = None, ubigeo: Ubigeo | None = None,
            estado: Literal["activa", "retirada"] | None = None,
            pagina: PaginaNumero = 1, tamano_pagina: TamanoPagina = 50):
    """El nivel visible y alerta_modelo por F1 se exponen por separado, con estado experimental."""
    if ubigeo:
        q.distrito_existente(sesion, ubigeo)
    return lectura(request, response, sesion, lambda: q.paginar(sesion,
        q.consulta_alertas(horizonte, ubigeo, estado), pagina, tamano_pagina,
        lambda a: q.alerta_dto(sesion, a, request.app.state.cfg)))


@router.get("/alertas/{identificador}", response_model=AlertaRespuesta, summary="Consultar alerta e indicadores que la sustentan")
def alerta(identificador: Identificador, request: Request, response: Response, sesion: Sesion):
    """Conserva el estado retirada y el motivo, sin presentar retrospectivas como vigentes."""
    def construir():
        a = sesion.get(Alerta, identificador)
        if a is None:
            raise ErrorAPI(404, "alerta_no_encontrada", "La alerta no existe")
        return q.alerta_dto(sesion, a, request.app.state.cfg)
    return lectura(request, response, sesion, construir)
