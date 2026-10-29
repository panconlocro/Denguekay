"""Health and the real geographic catalogue (HU0012-HU0016)."""

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from apps.api import queries as q
from apps.api.dependencies import PageNumber, DbSession, PageSize, Ubigeo, cached_read
from apps.api.contract import APP_VERSION
from apps.api.schemas import ConfiguracionRespuesta, DistritoRespuesta, Pagina, SaludRespuesta
from denguekay.db.models import District

router = APIRouter(tags=["Salud y distritos"])


@router.get("/salud", response_model=SaludRespuesta, summary="Comprobar API y conexión a la base de datos (HU0016)")
def salud(request: Request, sesion: DbSession):
    """Consulta la BD en cada solicitud y reporta la última ejecución exitosa."""
    return q.health(sesion, APP_VERSION)


@router.get("/configuracion", response_model=ConfiguracionRespuesta, tags=["Configuración"],
            summary="Horizontes disponibles, horizonte por defecto, cortes y leyenda (extensión)")
def configuracion(request: Request, response: Response, sesion: DbSession):
    """Los horizontes disponibles salen de las versiones en uso de la BD; nada queda en código duro en el frontend."""
    return cached_read(request, response, sesion, lambda: q.configuration(
        sesion, request.app.state.cfg.servir_no_validadas))


@router.get("/distritos", response_model=Pagina[DistritoRespuesta], summary="Listar distritos de Piura")
def distritos(request: Request, response: Response, sesion: DbSession,
              pagina: PageNumber = 1, tamano_pagina: PageSize = 65):
    """Catálogo con provincia, centroide y población censal 2017; ubigeo como texto."""
    return cached_read(request, response, sesion, lambda: q.paginate(sesion,
        select(District).order_by(District.ubigeo), pagina, tamano_pagina,
        lambda filas: [q.district_dto(d) for d in filas]))


@router.get("/distritos/{ubigeo}", response_model=DistritoRespuesta, summary="Consultar un distrito (extensión)")
def distrito(ubigeo: Ubigeo, request: Request, response: Response, sesion: DbSession):
    """Responde 404 si el código de seis dígitos no pertenece al catálogo."""
    return cached_read(request, response, sesion, lambda: q.district_dto(q.existing_district(sesion, ubigeo)))
