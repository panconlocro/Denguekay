"""Writes protected with X-API-Key: inference and activation (HU0009)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from apps.api import queries as q
from apps.api.dependencies import Identifier, DbSession, require_key
from apps.api.errors import APIError
from apps.api.schemas import ActivacionRespuesta, InferenciaRespuesta, SolicitudInferencia
from denguekay.db.models import Run, ModelVersion, utc_now
from denguekay.serving.artifacts import InvalidArtifact
from denguekay.serving.inference import InferenceUnavailable, infer
from denguekay.serving.parameters import MissingParameter

router = APIRouter(prefix="/admin", tags=["Administración"], dependencies=[Depends(require_key)])


def commit_and_invalidate(request, session):
    session.commit()
    request.app.state.cache.clear()
    request.app.openapi_schema = None


@router.post("/inferencias", response_model=InferenciaRespuesta,
             summary="Ejecutar la inferencia de una semana de corte (HU0009)")
def inferencias(solicitud: SolicitudInferencia, request: Request, sesion: DbSession):
    """Reconstruye los vectores desde la BD, aplica la versión en uso y hace UPSERT de predicciones y alertas.

    No entrena. Un horizonte sin modelo, un corte sin observaciones o un artefacto alterado responden 409.
    """
    try:
        result = infer(sesion, solicitud.horizonte, solicitud.id_semana_corte,
                            storage=request.app.state.storage,
                            servir_no_validadas=request.app.state.cfg.servir_no_validadas, origin="api")
    except (InferenceUnavailable, InvalidArtifact, MissingParameter) as error:
        sesion.rollback()
        # The failed attempt is audited, as in the load and the publication.
        sesion.add(Run(tipo="inferencia", estado="fallida", fin=utc_now(),
                             detalle={"origen": "api", "horizonte": solicitud.horizonte,
                                      "id_semana_corte": solicitud.id_semana_corte},
                             mensaje_error=f"{type(error).__name__}: {error}"[:2000]))
        sesion.commit()
        request.app.state.cache.clear()
        if isinstance(error, MissingParameter):
            raise APIError(503, "parametros_no_configurados", str(error)) from error
        codigo = "artefacto_invalido" if isinstance(error, InvalidArtifact) else "inferencia_no_disponible"
        raise APIError(409, codigo, str(error)) from error
    commit_and_invalidate(request, sesion)
    return {k: result[k] for k in InferenciaRespuesta.model_fields}


def sibling(sesion, version):
    """The other task of the same package and horizon (decision M3), if the package has it."""
    return sesion.scalar(select(ModelVersion).where(
        ModelVersion.horizonte == version.horizonte, ModelVersion.tarea != version.tarea,
        ModelVersion.ruta_artefacto == version.ruta_artefacto,
        ModelVersion.sha256_artefacto == version.sha256_artefacto,
    ).order_by(ModelVersion.id_version.desc()).limit(1).with_for_update())


def check_activable(version):
    if not version.cumple_umbrales:
        raise APIError(409, "no_cumple_umbrales",
                       f"La versión {version.codigo} no cumple los umbrales de aceptación; se sirve solo como experimental")
    if version.estado == "rechazada":
        raise APIError(409, "version_rechazada", "Una versión rechazada no se puede activar")


@router.post("/modelos/{version}/activar", response_model=ActivacionRespuesta,
             summary="Activar una versión que cumple los umbrales (HU0009)")
def activar(version: Identifier, request: Request, sesion: DbSession):
    """Archiva la versión activa de la misma tarea y horizonte, en una transacción auditada.

    Una versión con cumple_umbrales = false no se activa (409): así lo exige el DDL.
    """
    # The docstring above is part of the frozen v1 contract (OpenAPI description). Decision M3: both tasks
    # of a horizon come from one package, so the sibling version of that package is activated too and the
    # active versions of both tasks are archived; the response notes it in ``nota``.
    new = sesion.scalar(select(ModelVersion).where(ModelVersion.id_version == version).with_for_update())
    if new is None:
        raise APIError(404, "modelo_no_encontrado", "La versión de modelo no existe")
    check_activable(new)
    if new.estado == "activa":
        raise APIError(409, "ya_activa", "La versión ya está activa")
    pair = [new]
    other = sibling(sesion, new)
    # A rejected or non-compliant sibling stops the pair: a horizon never mixes tasks of two packages.
    if other is not None and other.estado != "activa":
        check_activable(other)
        pair.append(other)
    now = utc_now()
    archived = {}
    for v in pair:
        previous = sesion.scalar(select(ModelVersion).where(
            ModelVersion.tarea == v.tarea, ModelVersion.horizonte == v.horizonte,
            ModelVersion.estado == "activa").with_for_update())
        if previous is not None:
            previous.estado = "archivada"
            archived[v.tarea] = previous
    sesion.flush()  # frees the partial unique index before activating the new ones
    for v in pair:
        v.estado, v.fecha_activacion = "activa", now
    previous = archived.get(new.tarea)
    run = Run(tipo="mantenimiento", estado="exitosa", fin=now, detalle={
        "accion": "activacion", "version": new.codigo, "id_version": new.id_version,
        "archivada": previous.codigo if previous else None,
        "activadas": [v.codigo for v in pair], "archivadas": [v.codigo for v in archived.values()]})
    sesion.add(run)
    sesion.flush()
    note = "La activación no recalcula predicciones: ejecute POST /admin/inferencias"
    if len(pair) == 2:
        note = f"Se activó también {pair[1].codigo} (misma pareja del paquete). " + note
    response = {"id_ejecucion": run.id_ejecucion, "activada": q.model_dto(new),
                 "archivada": q.model_dto(previous) if previous else None, "nota": note}
    commit_and_invalidate(request, sesion)
    return response
