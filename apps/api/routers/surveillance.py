"""Dashboard, risk map and alerts (HU0012, HU0014, HU0015)."""

from typing import Literal

from fastapi import APIRouter, Request, Response

from apps.api import queries as q
from apps.api.dependencies import Horizon, Identifier, PageNumber, DbSession, PageSize, Ubigeo, cached_read
from apps.api.errors import APIError
from apps.api.schemas import AlertaRespuesta, MapaRiesgoRespuesta, Pagina, TableroRespuesta
from denguekay.db.models import Alert

router = APIRouter(tags=["Vigilancia"])


@router.get("/tablero/resumen", response_model=TableroRespuesta, summary="Resumen del corte vigente (HU0012)")
def tablero(request: Request, response: Response, sesion: DbSession, horizonte: Horizon):
    """Niveles de riesgo, alertas activas y casos; la suma regional es null si falta algún distrito."""
    return cached_read(request, response, sesion, lambda: q.dashboard(
        sesion, horizonte, request.app.state.cfg.servir_no_validadas))


@router.get("/mapa-riesgo", response_model=MapaRiesgoRespuesta, summary="Mapa de riesgo GeoJSON (HU0014)")
def mapa_riesgo(request: Request, response: Response, sesion: DbSession, horizonte: Horizon):
    """FeatureCollection con una geometría por distrito (hoy Point, el centroide) y su nivel de riesgo o Sin datos."""
    return cached_read(request, response, sesion, lambda: q.risk_map(
        sesion, horizonte, request.app.state.cfg.servir_no_validadas))


@router.get("/alertas", response_model=Pagina[AlertaRespuesta], summary="Listar alertas (HU0015)")
def alertas(request: Request, response: Response, sesion: DbSession,
            horizonte: Horizon | None = None, ubigeo: Ubigeo | None = None,
            nivel: Literal["alto", "muy_alto"] | None = None,
            estado: Literal["activa", "retirada"] | None = None,
            pagina: PageNumber = 1, tamano_pagina: PageSize = 50):
    """Filtros por horizonte, distrito y nivel (Tabla 2); ``estado`` es un filtro extra."""
    if ubigeo:
        q.existing_district(sesion, ubigeo)
    return cached_read(request, response, sesion, lambda: q.paginate(sesion,
        q.alerts_query(horizonte, ubigeo, nivel, estado), pagina, tamano_pagina,
        lambda filas: q.alert_dtos(sesion, filas)))


@router.get("/alertas/{identificador}", response_model=AlertaRespuesta, summary="Consultar una alerta (extensión)")
def alerta(identificador: Identifier, request: Request, response: Response, sesion: DbSession):
    """Incluye la predicción que la sustenta; conserva estado retirado y motivo."""
    def build():
        a = sesion.get(Alert, identificador)
        if a is None:
            raise APIError(404, "alerta_no_encontrada", "La alerta no existe")
        return q.alert_dtos(sesion, [a])[0]
    return cached_read(request, response, sesion, build)
