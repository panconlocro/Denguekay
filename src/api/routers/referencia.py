"""Salud y catálogo geográfico real."""

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from src.api import consultas as q
from src.api.dependencias import PaginaNumero, Sesion, TamanoPagina, Ubigeo, lectura
from src.api.esquemas import (DistritoRespuesta, GeojsonRespuesta, Pagina, SaludRespuesta)
from src.db.modelos import Distrito

router = APIRouter(tags=["Salud y distritos"])


@router.get("/salud", response_model=SaludRespuesta, summary="Comprobar API y conexión a la base de datos")
def salud(sesion: Sesion):
    """Comprueba la BD en cada solicitud y reporta versiones activas y último corte."""
    return q.salud(sesion)


@router.get("/distritos", response_model=Pagina[DistritoRespuesta], summary="Listar distritos con paginación")
def distritos(request: Request, response: Response, sesion: Sesion,
              pagina: PaginaNumero = 1, tamano_pagina: TamanoPagina = 65):
    """Devuelve el catálogo cargado desde reference, con códigos ubigeo como texto."""
    return lectura(request, response, sesion, lambda: q.paginar(sesion,
        select(Distrito).order_by(Distrito.ubigeo), pagina, tamano_pagina,
        lambda d: q.distrito_dto(d, q.metadatos(sesion))))


@router.get("/distritos/geojson", response_model=GeojsonRespuesta, summary="Obtener mapa GeoJSON de distritos")
def geojson(request: Request, response: Response, sesion: Sesion):
    """Usa geometrías guardadas o puntos de centroides reales; nunca inventa polígonos."""
    return lectura(request, response, sesion, lambda: q.geojson(sesion))


@router.get("/distritos/{ubigeo}", response_model=DistritoRespuesta, summary="Consultar un distrito por ubigeo")
def distrito(ubigeo: Ubigeo, request: Request, response: Response, sesion: Sesion):
    """Responde 404 si el código de seis dígitos no pertenece al catálogo."""
    return lectura(request, response, sesion, lambda: q.distrito_dto(q.distrito_existente(sesion, ubigeo), q.metadatos(sesion)))
