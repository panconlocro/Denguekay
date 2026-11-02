"""Registration of a package's versions according to the OE2 document (decision M3).

A package gives one ``version_modelo`` row per task and horizon; every row points to the same
manifest (``ruta_artefacto``, ``sha256_artefacto``). What each type trains lives in its predictor
(``denguekay.serving.predictors``); this module only stores the result.
"""

from sqlalchemy import select

from denguekay.db.models import VariableImportance, ModelVersion
from denguekay.evaluation.acceptance import evaluate_model_validation


def meets_thresholds(task, metrics, criteria):
    """parametro_sistema thresholds applied to the saved metrics of the deciding block."""
    return evaluate_model_validation(task, metrics, criteria)["estado_validacion"] == "validado"


def thresholds(built, criteria):
    """{(horizon, task): cumple_umbrales} of a package's versions."""
    return {(spec.horizonte, spec.tarea): meets_thresholds(spec.tarea, spec.data["metricas"], criteria)
            for spec in built.versions}


def next_code(sesion, prefix):
    """``<prefix><n>`` with the next free number (e.g. ``clf-h2-v`` -> ``clf-h2-v3``)."""
    existing = sesion.scalars(select(ModelVersion.codigo).where(ModelVersion.codigo.like(f"{prefix}%")))
    numbers = [int(c.removeprefix(prefix)) for c in existing if c.removeprefix(prefix).isdigit()]
    return f"{prefix}{max(numbers, default=0) + 1}"


def save_versions(sesion, built, path, sha256, mlflow_run_id, meets):
    """Register each version as ``candidata``; the same package and dataset reuse their version.

    ``meets`` = ``thresholds(built, criteria)``. Returns {(horizon, task): ModelVersion}.
    """
    result = {}
    for spec in built.versions:
        version = sesion.scalar(select(ModelVersion).where(
            ModelVersion.tarea == spec.tarea, ModelVersion.horizonte == spec.horizonte,
            ModelVersion.sha256_artefacto == sha256,
            ModelVersion.sha256_dataset == spec.data["sha256_dataset"]))
        if version is None:
            version = ModelVersion(**spec.data, tarea=spec.tarea, horizonte=spec.horizonte,
                                   codigo=next_code(sesion, spec.code_prefix), ruta_artefacto=path,
                                   sha256_artefacto=sha256, estado="candidata", mlflow_run_id=mlflow_run_id,
                                   cumple_umbrales=meets[spec.horizonte, spec.tarea])
            sesion.add(version)
            sesion.flush()
            for importance in spec.importances:
                sesion.add(VariableImportance(id_version=version.id_version, **importance))
            sesion.flush()
        result[spec.horizonte, spec.tarea] = version
    return result
