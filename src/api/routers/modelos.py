"""Modelo en uso, detalle de versiones e importancias (HU0008)."""

from fastapi import APIRouter, Request, Response

from src.api import consultas as q
from src.api.dependencias import Horizonte, Identificador, Sesion, lectura
from src.api.esquemas import ModeloDetalle, ModelosActivosRespuesta, VariablesRespuesta

router = APIRouter(tags=["Modelos"])


@router.get("/modelos/activo", response_model=ModelosActivosRespuesta, summary="Versiones en uso por horizonte (HU0008)")
def modelos_activos(request: Request, response: Response, sesion: Sesion, horizonte: Horizonte | None = None):
    """Versión activa por tarea; sin activa, la selección experimental marcada ``experimental: true``."""
    return lectura(request, response, sesion, lambda: q.modelos_en_uso(
        sesion, horizonte, request.app.state.cfg.servir_no_validadas))


@router.get("/modelos/{identificador}", response_model=ModeloDetalle, summary="Detalle de una versión (extensión)")
def modelo(identificador: Identificador, request: Request, response: Response, sesion: Sesion):
    """Variables, hiperparámetros, métricas por bloque, hashes y reproducibilidad."""
    return lectura(request, response, sesion, lambda: q.modelo_dto(q.modelo_existente(sesion, identificador), True))


@router.get("/modelos/{identificador}/variables", response_model=VariablesRespuesta,
            summary="Importancias gain de una versión (extensión, HU0008-4)")
def variables(identificador: Identificador, request: Request, response: Response, sesion: Sesion):
    """Las importancias no implican causalidad; su ausencia se informa sin rellenar con ceros."""
    return lectura(request, response, sesion, lambda: q.variables(sesion, identificador))
