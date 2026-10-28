"""Serving fit with train.py and version registration according to the OE2 document.

Training does not change: it reuses ``fit_models``, the base hyperparameters
and the variants of the compact protocol. This module only packages the result
(booster to Storage, metadata to ``version_modelo``).
"""

from dataclasses import dataclass
import platform

import pandas as pd
from sqlalchemy import select
from xgboost import __version__ as XGBOOST_VERSION

from denguekay.db.models import VariableImportance, ModelVersion
from denguekay.model.device import xgboost_settings
from denguekay.model.train import BASE_PARAMS, fit_models
from denguekay.evaluation.compact_validation import compact_variants
from denguekay.serving.artifacts import serialize_booster, sha256_bytes
from denguekay.serving.protocol import variant_metrics
from denguekay.evaluation.acceptance import evaluate_model_validation

PREFIXES = {"clasificacion": "clf", "regresion": "reg"}


@dataclass
class PreparedVersion:
    data: dict
    artifact: bytes
    importances: list


def _partition(metrics):
    fields = ("bloque", "tipo", "corte_ajuste", "primera_semana_objetivo", "ultima_semana_objetivo",
              "n_entrenamiento", "n_prueba", "calibracion")
    return {name: {c: f[c] for c in fields if c in f} for name, f in metrics["bloques"].items()}


def train_service_versions(protocol, horizons, cfg, cutoff):
    """Use every label closed at the cutoff and the same functions/hyperparameters.

    ``fit_models`` returns both targets; the component selected by configuration
    is kept, without changing the training logic.
    """
    versions = {}
    for h in horizons:
        source = protocol.data[h]
        train = source.loc[(source.semana_inicio + pd.Timedelta(days=6)).le(pd.Timestamp(cutoff))].copy()
        if train.empty or train.brote.nunique() != 2:
            raise ValueError("El ajuste final requiere etiquetas cerradas y ambas clases")
        pairs = {name: fit_models(train, compact_variants(h)[name]) for name in set(cfg.variantes.values())}
        evaluation = protocol.report
        for task, name in cfg.variantes.items():
            model = pairs[name][1 if task == "clasificacion" else 0]
            metrics = variant_metrics(protocol, h, name)
            artifact = serialize_booster(model)
            data = {
                "tarea": task, "horizonte": h, "algoritmo": "xgboost",
                "variables": compact_variants(h)[name], "hiperparametros": dict(BASE_PARAMS),
                "metricas": metrics,
                "umbral_probabilidad": (metrics["bloques"]["calendario_2025"]["clasificacion"]["umbral_probabilidad"]
                                        if task == "clasificacion" else None),
                "sha256_dataset": evaluation["horizontes"][str(h)]["sha256_gold"],
                "sha256_artefacto": sha256_bytes(artifact),
                "reproducibilidad": {
                    "variante": name, "device": xgboost_settings()["device"],
                    "version_xgboost": XGBOOST_VERSION,
                    "plataforma": f"{platform.system()} {platform.release()} {platform.machine()}",
                    "entrenamiento_inicio": str(train.semana_inicio.min().date()),
                    "entrenamiento_corte": str(cutoff),
                    "sha256_manifiesto_gold": evaluation["sha256_manifest_gold"],
                    "particion_temporal": {"bloques": _partition(metrics),
                                           "criterio_seleccion": evaluation["criterio_seleccion"],
                                           "nota_2024": evaluation["nota_2024"],
                                           "alcance": "Servicio: ajuste con etiquetas cerradas al corte"}},
            }
            gains = model.get_booster().get_score(importance_type="gain")
            importances = [{"variable": c, "importancia": float(g), "rango": span}
                            for span, (c, g) in enumerate(sorted(gains.items(), key=lambda x: (-x[1], x[0])), 1)]
            versions[h, task] = PreparedVersion(data, artifact, importances)
    return versions


def meets_thresholds(task, metrics, criteria):
    """parametro_sistema thresholds applied to the saved metrics of the deciding block."""
    return evaluate_model_validation(task, metrics, criteria)["estado_validacion"] == "validado"


def next_code(sesion, task, horizon):
    prefix = f"{PREFIXES[task]}-h{horizon}-v"
    existing = sesion.scalars(select(ModelVersion.codigo).where(ModelVersion.codigo.like(f"{prefix}%")))
    numbers = [int(c.removeprefix(prefix)) for c in existing if c.removeprefix(prefix).isdigit()]
    return f"{prefix}{max(numbers, default=0) + 1}"


def artifact_path(storage, code, content):
    """``modelos/<codigo>.json``; it never overwrites a different artifact.

    Another local database (e.g. the test one) may have already saved that code
    with another booster: then a name with the SHA-256 is used, without overwriting
    the other one.
    """
    path = f"modelos/{code}.json"
    if storage.exists(path):
        if sha256_bytes(storage.read(path)) == sha256_bytes(content):
            return path
        path = f"modelos/{code}-{sha256_bytes(content)[:12]}.json"
    if not storage.exists(path):
        storage.save(path, content)
    return path


def save_versions(sesion, prepared_versions, mlflow_run_id, criteria, storage):
    """Register each version as ``candidata``; the same artifact reuses its version.

    The booster is saved in ``modelos/<codigo>.json`` and its hash stays in the database.
    """
    result = {}
    for key, prepared in prepared_versions.items():
        data = prepared.data
        version = sesion.scalar(select(ModelVersion).where(
            ModelVersion.tarea == data["tarea"], ModelVersion.horizonte == data["horizonte"],
            ModelVersion.sha256_artefacto == data["sha256_artefacto"],
            ModelVersion.sha256_dataset == data["sha256_dataset"]))
        if version is None:
            code = next_code(sesion, data["tarea"], data["horizonte"])
            path = artifact_path(storage, code, prepared.artifact)
            version = ModelVersion(**data, codigo=code, ruta_artefacto=path, estado="candidata",
                                    mlflow_run_id=mlflow_run_id,
                                    cumple_umbrales=meets_thresholds(data["tarea"], data["metricas"], criteria))
            sesion.add(version)
            sesion.flush()
            for importance in prepared.importances:
                sesion.add(VariableImportance(id_version=version.id_version, **importance))
            sesion.flush()
        result[key] = version
    return result


def service_report(prepared_versions, protocol, cutoff):
    """Standard shape for MLflow; the time metrics are imported, not from this fit."""
    report = {"experimento": "versiones_de_servicio", "parametros": dict(BASE_PARAMS),
               "version_xgboost": XGBOOST_VERSION, "fecha_corte_datos": str(cutoff),
               "device_evaluacion_importada": protocol.report["parametros"]["device"],
               "evaluacion_generada_en_esta_corrida": False,
               "nota_metricas": "Las métricas temporales importadas se adjuntan como evidencia histórica; no son una evaluación del ajuste final",
               "sha256_manifest_gold": protocol.report["sha256_manifest_gold"], "horizontes": {}}
    for (h, task), prepared in prepared_versions.items():
        data = prepared.data
        block = report["horizontes"].setdefault(str(h), {
            "archivo_gold": protocol.report["horizontes"][str(h)]["archivo_gold"],
            "sha256_gold": data["sha256_dataset"], "variantes": {}})
        block["variantes"][f"{data['reproducibilidad']['variante']}_{task}"] = {
            "columnas": data["variables"], "tipo_modelo": task, "corte_ajuste_servicio": str(cutoff),
            "umbral_probabilidad": data["umbral_probabilidad"], "sha256_artefacto": data["sha256_artefacto"]}
    return report
