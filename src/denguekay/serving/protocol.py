"""Import the OOS predictions and check them against the original progressive protocol."""

from dataclasses import dataclass
import hashlib
import json

import numpy as np
import pandas as pd

from denguekay.model.train import evaluate_fold, prepare_gold, split_season, split_calendar_year
from denguekay.evaluation.compact_validation import run_compact_validation, compact_variants
from denguekay.config.paths import (GOLD, GOLD_MANIFEST, COMPACT_METRICS, COMPACT_PREDICTIONS,
                             SERVING_REGENERATED_PROTOCOL, SILVER_INTEGRATED)
from denguekay.data.validation.gx_quality import read_gold
from denguekay.data.validation.forecast_contract import KEY


@dataclass
class Protocol:
    report: dict
    predictions: pd.DataFrame
    data: dict
    partitions: dict
    hashes: dict
    metrics_path: object
    predictions_path: object


def load_protocol(horizons, variants, *, metrics_path=COMPACT_METRICS,
                    predictions_path=COMPACT_PREDICTIONS):
    """If the CSV is missing, regenerate it in models/serving without overwriting Rosa's."""
    if not predictions_path.exists():
        metrics_path = SERVING_REGENERATED_PROTOCOL / "metricas.json"
        predictions_path = SERVING_REGENERATED_PROTOCOL / "predicciones_por_bloque.csv"
        if not predictions_path.exists() or not metrics_path.exists():
            print("Falta el CSV OOS: se ejecutará el protocolo existente en models/serving")
            run_compact_validation(output_dir=SERVING_REGENERATED_PROTOCOL,
                metrics_path=metrics_path)
    report = json.loads(metrics_path.read_text(encoding="utf-8"))
    pred = pd.read_csv(predictions_path, dtype={"ubigeo": "string"},
                       parse_dates=["semana_inicio", "origen_cierre"])
    required = {*KEY, "semana_inicio", "origen_cierre", "horizonte", "variante", "bloque",
                  "casos_Dengue", "brote", "umbral_brote_casos", "probabilidad_brote", "casos_predichos"}
    if not required <= set(pred) or pred.duplicated([*KEY, "horizonte", "variante", "bloque"]).any():
        raise ValueError("El CSV OOS tiene columnas ausentes o llaves duplicadas")
    if report["sha256_manifest_gold"] != hashlib.sha256(GOLD_MANIFEST.read_bytes()).hexdigest():
        raise ValueError("El protocolo temporal no corresponde al manifiesto gold actual")
    data, partitions = {}, {}
    for h in horizons:
        gold, file = read_gold(GOLD, h)
        block_h = report["horizontes"].get(str(h))
        if not block_h or block_h["sha256_gold"] != hashlib.sha256(file.read_bytes()).hexdigest():
            raise ValueError(f"Las métricas h={h} no corresponden al gold actual")
        data[h], _ = prepare_gold(gold, h)
        for name in set(variants.values()):
            cols = compact_variants(h).get(name)
            result = block_h["variantes"].get(name)
            if not result or cols != result["columnas"]:
                raise ValueError("Las columnas del protocolo no coinciden con el contrato de variantes")
            folds = [*result["folds"], result["sensibilidad_2025"]]
            for fold in folds:
                block = fold["bloque"]
                train, test_set, cutoff = (split_calendar_year(data[h], 2025) if block == "calendario_2025"
                                        else split_season(data[h], int(block.split("_")[-1])))
                if str(cutoff.date()) != fold["corte_ajuste"] or len(train) != fold["n_entrenamiento"]:
                    raise ValueError("El corte de entrenamiento difiere del protocolo guardado")
                selection = pred.loc[pred.horizonte.eq(h) & pred.variante.eq(name) & pred.bloque.eq(block)]
                check_block(selection, test_set, fold, h, name)
                partitions[h, name, block] = {"inicio_entrenamiento": train.semana_inicio.min().date(),
                    "corte": cutoff.date(), "fold": fold}
    hashes = {"protocolo_metricas": hashlib.sha256(metrics_path.read_bytes()).hexdigest(),
              "protocolo_predicciones": hashlib.sha256(predictions_path.read_bytes()).hexdigest()}
    return Protocol(report, pred, data, partitions, hashes, metrics_path, predictions_path)


def check_block(pred, test_set, fold, horizon, variant):
    """Check coverage, targets, origin and metrics without changing their values."""
    if len(pred) != len(test_set) or set(map(tuple, pred[KEY].to_numpy())) != set(map(tuple, test_set[KEY].to_numpy())):
        raise ValueError(f"Las predicciones OOS no cubren el bloque {fold['bloque']}")
    columns = ["semana_inicio", "origen_cierre", "casos_Dengue", "brote", "umbral_brote_casos"]
    p = pred.sort_values(KEY).reset_index(drop=True).copy()
    real = test_set.sort_values(KEY).reset_index(drop=True)
    for c in columns[:2]:
        if not p[c].equals(real[c]):
            raise ValueError("Las fechas de las predicciones no coinciden con el corte temporal")
    for c in columns[2:]:
        if not np.allclose(p[c].to_numpy(float), real[c].to_numpy(float), rtol=1e-12, atol=1e-12):
            raise ValueError("El observado o etiqueta del CSV OOS difiere de gold")
    lag = f"casos_lag_{horizon}"
    if lag not in p or not np.array_equal(p[lag].to_numpy(float), real[lag].to_numpy(float)):
        raise ValueError("La persistencia del CSV OOS difiere del predictor de gold")
    # XGBoost exported float32. Restoring that type reproduces the evaluation
    # JSON; the original CSV values are kept for the import.
    for c in ("probabilidad_brote", "casos_predichos"):
        p[c] = p[c].astype("float32")
    computed = evaluate_fold(p, horizon=horizon, variant=variant, block=fold["bloque"],
        kind=fold["tipo"], cutoff=pd.Timestamp(fold["corte_ajuste"]), n_training=fold["n_entrenamiento"],
        classification_threshold=fold["clasificacion"]["umbral_probabilidad"])
    for kind in ("clasificacion", "regresion", "persistencia"):
        _compare_metrics(computed[kind], fold[kind])


def _compare_metrics(actual, saved):
    for key, expected_value in saved.items():
        if isinstance(expected_value, dict):
            _compare_metrics(actual[key], expected_value)
        elif expected_value is None:
            if actual[key] is not None:
                raise ValueError("Una métrica ausente no puede sustituirse por cero")
        elif not np.isclose(actual[key], expected_value, rtol=1e-10, atol=1e-10):
            raise ValueError(f"Las predicciones OOS no reproducen la métrica guardada: {key}")


def variant_metrics(protocol, horizon, variant):
    """Keep selection, contrast and sensitivity apart, without averaging them."""
    result = protocol.report["horizontes"][str(horizon)]["variantes"][variant]
    return {"bloques": {f["bloque"]: f for f in [*result["folds"], result["sensibilidad_2025"]]},
            "procedencia": "Protocolo temporal progresivo; métricas de versiones por bloque, no del ajuste final",
            "sha256_reporte": protocol.hashes["protocolo_metricas"],
            "sha256_predicciones": protocol.hashes["protocolo_predicciones"],
            "device_evaluacion": protocol.report["parametros"]["device"],
            "version_xgboost_evaluacion": protocol.report["version_xgboost"]}
