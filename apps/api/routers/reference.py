"""Salud y catálogo geográfico real (HU0012-HU0016)."""

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from apps.api import queries as q
from apps.api.dependencies import PaginaNumero, Sesion, TamanoPagina, Ubigeo, lectura
from apps.api.schemas import DistritoRespuesta, Pagina, SaludRespuesta
from denguekay.db.models import District

router = APIRouter(tags=["Salud y distritos"])


@router.get("/salud", response_model=SaludRespuesta, summary="Comprobar API y conexión a la base de datos (HU0016)")
def salud(request: Request, sesion: Sesion):
    """Consulta la BD en cada solicitud y reporta la última ejecución exitosa."""
    return q.salud(sesion, request.app.version)


@router.get("/distritos", response_model=Pagina[DistritoRespuesta], summary="Listar distritos de Piura")
def distritos(request: Request, response: Response, sesion: Sesion,
              pagina: PaginaNumero = 1, tamano_pagina: TamanoPagina = 65):
    """Catálogo con provincia, centroide y población censal 2017; ubigeo como texto."""
    return lectura(request, response, sesion, lambda: q.paginar(sesion,
        select(District).order_by(District.ubigeo), pagina, tamano_pagina,
        lambda filas: [q.distrito_dto(d) for d in filas]))


@router.get("/distritos/{ubigeo}", response_model=DistritoRespuesta, summary="Consultar un distrito (extensión)")
def distrito(ubigeo: Ubigeo, request: Request, response: Response, sesion: Sesion):
    """Responde 404 si el código de seis dígitos no pertenece al catálogo."""
    return lectura(request, response, sesion, lambda: q.distrito_dto(q.distrito_existente(sesion, ubigeo)))
