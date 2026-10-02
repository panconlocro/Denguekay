"""Versiones, evaluación temporal, importancias y activación auditada."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select

from src.api import consultas as q
from src.api.dependencias import Horizonte, Identificador, PaginaNumero, Sesion, TamanoPagina, exigir_clave, lectura
from src.api.esquemas import ModeloDetalle, ModeloRespuesta, Pagina, ReevaluacionRespuesta, VariablesRespuesta
from src.api.routers.datos import publicar_reevaluacion
from src.db.modelos import VersionModelo

router = APIRouter(tags=["Modelos"])


@router.get("/modelos", response_model=Pagina[ModeloRespuesta], summary="Listar versiones de servicio y versiones históricas")
def modelos(request: Request, response: Response, sesion: Sesion,
            horizonte: Horizonte | None = None, pagina: PaginaNumero = 1,
            tamano_pagina: TamanoPagina = 50):
    """La validación se calcula a partir de las métricas guardadas; activa no equivale a validada."""
    consulta = select(VersionModelo).order_by(VersionModelo.id.desc())
    if horizonte:
        consulta = consulta.where(VersionModelo.horizonte == horizonte)
    return lectura(request, response, sesion, lambda: q.paginar(sesion,
        consulta, pagina, tamano_pagina, lambda v: q.modelo_dto(v, q.metadatos(sesion))))


@router.get("/modelos/{identificador}", response_model=ModeloDetalle, summary="Consultar métricas por bloque y particiones temporales")
def modelo(identificador: Identificador, request: Request, response: Response, sesion: Sesion):
    """Expone corte, columnas, parámetros y reproducibilidad; no promedia 2024 con 2025."""
    return lectura(request, response, sesion, lambda: q.modelo_dto(q.modelo_existente(sesion, identificador), q.metadatos(sesion), True))


@router.get("/modelos/{identificador}/variables", response_model=VariablesRespuesta, summary="Consultar importancias gain guardadas de una versión")
def variables(identificador: Identificador, request: Request, response: Response, sesion: Sesion):
    """Las importancias no implican causalidad; su ausencia se informa sin rellenar con ceros."""
    return lectura(request, response, sesion, lambda: q.variables(sesion, identificador))


@router.post("/modelos/{identificador}/activar", response_model=ReevaluacionRespuesta,
             dependencies=[Depends(exigir_clave)], summary="Activar otra versión y recalcular preservando el historial")
def activar(identificador: Identificador, request: Request, sesion: Sesion):
    """Exige X-API-Key. Solo admite artefactos de servicio compatibles con los vectores vigentes.

    La operación es atómica: un error conserva la selección y las predicciones
    anteriores. Seleccionar una versión experimental no la promueve a producción.
    """
    candidata = q.modelo_existente(sesion, identificador)
    return publicar_reevaluacion(request, sesion, candidata.horizonte, candidata)
