"""Salud y catálogo geográfico real (HU0012-HU0016)."""

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from src.api import consultas as q
from src.api.dependencias import PaginaNumero, Sesion, TamanoPagina, Ubigeo, lectura
from src.api.esquemas import DistritoRespuesta, Pagina, SaludRespuesta
from src.db.modelos import Distrito

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
        select(Distrito).order_by(Distrito.ubigeo), pagina, tamano_pagina,
        lambda filas: [q.distrito_dto(d) for d in filas]))


@router.get("/distritos/{ubigeo}", response_model=DistritoRespuesta, summary="Consultar un distrito (extensión)")
def distrito(ubigeo: Ubigeo, request: Request, response: Response, sesion: Sesion):
    """Responde 404 si el código de seis dígitos no pertenece al catálogo."""
    return lectura(request, response, sesion, lambda: q.distrito_dto(q.distrito_existente(sesion, ubigeo)))
