"""Model in use, version detail and importances (HU0008)."""

from fastapi import APIRouter, Request, Response

from apps.api import queries as q
from apps.api.dependencies import Horizon, Identifier, DbSession, cached_read
from apps.api.schemas import ModeloDetalle, ModelosActivosRespuesta, VariablesRespuesta

router = APIRouter(tags=["Modelos"])


@router.get("/modelos/activo", response_model=ModelosActivosRespuesta, summary="Versiones en uso por horizonte (HU0008)")
def modelos_activos(request: Request, response: Response, sesion: DbSession, horizonte: Horizon | None = None):
    """Versión activa por tarea; sin activa, la selección experimental marcada ``experimental: true``."""
    return cached_read(request, response, sesion, lambda: q.models_in_use(
        sesion, horizonte, request.app.state.cfg.servir_no_validadas))


@router.get("/modelos/{identificador}", response_model=ModeloDetalle, summary="Detalle de una versión (extensión)")
def modelo(identificador: Identifier, request: Request, response: Response, sesion: DbSession):
    """Variables, hiperparámetros, métricas por bloque, hashes y reproducibilidad."""
    return cached_read(request, response, sesion, lambda: q.model_dto(q.existing_model(sesion, identificador), True))


@router.get("/modelos/{identificador}/variables", response_model=VariablesRespuesta,
            summary="Importancias gain de una versión (extensión, HU0008-4)")
def variables(identificador: Identifier, request: Request, response: Response, sesion: DbSession):
    """Las importancias no implican causalidad; su ausencia se informa sin rellenar con ceros."""
    return cached_read(request, response, sesion, lambda: q.variables(sesion, identificador))
