"""Escrituras protegidas con X-API-Key: inferencia y activación (HU0009)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from src.api import consultas as q
from src.api.dependencias import Identificador, Sesion, exigir_clave
from src.api.errores import ErrorAPI
from src.api.esquemas import ActivacionRespuesta, InferenciaRespuesta, SolicitudInferencia
from src.db.modelos import Ejecucion, VersionModelo, ahora_utc
from src.serving.artefactos import ArtefactoInvalido
from src.serving.inferencia import InferenciaNoDisponible, inferir

router = APIRouter(prefix="/admin", tags=["Administración"], dependencies=[Depends(exigir_clave)])


def confirmar(request, sesion):
    sesion.commit()
    request.app.state.cache.limpiar()
    request.app.openapi_schema = None


@router.post("/inferencias", response_model=InferenciaRespuesta,
             summary="Ejecutar la inferencia de una semana de corte (HU0009)")
def inferencias(solicitud: SolicitudInferencia, request: Request, sesion: Sesion):
    """Reconstruye los vectores desde la BD, aplica la versión en uso y hace UPSERT de predicciones y alertas.

    No entrena. h=3, un corte sin observaciones o un artefacto alterado responden 409.
    """
    try:
        resultado = inferir(sesion, solicitud.horizonte, solicitud.id_semana_corte,
                            almacenamiento=request.app.state.almacenamiento,
                            servir_no_validadas=request.app.state.cfg.servir_no_validadas, origen="api")
    except (InferenciaNoDisponible, ArtefactoInvalido) as error:
        sesion.rollback()
        codigo = "artefacto_invalido" if isinstance(error, ArtefactoInvalido) else "inferencia_no_disponible"
        raise ErrorAPI(409, codigo, str(error)) from error
    confirmar(request, sesion)
    return {k: resultado[k] for k in InferenciaRespuesta.model_fields}


@router.post("/modelos/{version}/activar", response_model=ActivacionRespuesta,
             summary="Activar una versión que cumple los umbrales (HU0009)")
def activar(version: Identificador, request: Request, sesion: Sesion):
    """Archiva la versión activa de la misma tarea y horizonte, en una transacción auditada.

    Una versión con cumple_umbrales = false no se activa (409): así lo exige el DDL.
    """
    nueva = sesion.scalar(select(VersionModelo).where(VersionModelo.id_version == version).with_for_update())
    if nueva is None:
        raise ErrorAPI(404, "modelo_no_encontrado", "La versión de modelo no existe")
    if not nueva.cumple_umbrales:
        raise ErrorAPI(409, "no_cumple_umbrales",
                       "La versión no cumple los umbrales de aceptación; se sirve solo como experimental")
    if nueva.estado == "activa":
        raise ErrorAPI(409, "ya_activa", "La versión ya está activa")
    anterior = sesion.scalar(select(VersionModelo).where(
        VersionModelo.tarea == nueva.tarea, VersionModelo.horizonte == nueva.horizonte,
        VersionModelo.estado == "activa").with_for_update())
    ahora = ahora_utc()
    if anterior is not None:
        anterior.estado = "archivada"
        sesion.flush()  # libera el índice único parcial antes de activar la nueva
    nueva.estado, nueva.fecha_activacion = "activa", ahora
    ejecucion = Ejecucion(tipo="mantenimiento", estado="exitosa", fin=ahora, detalle={
        "accion": "activacion", "version": nueva.codigo, "id_version": nueva.id_version,
        "archivada": anterior.codigo if anterior else None})
    sesion.add(ejecucion)
    sesion.flush()
    respuesta = {"id_ejecucion": ejecucion.id_ejecucion, "activada": q.modelo_dto(nueva),
                 "archivada": q.modelo_dto(anterior) if anterior else None,
                 "nota": "La activación no recalcula predicciones: ejecute POST /admin/inferencias"}
    confirmar(request, sesion)
    return respuesta
