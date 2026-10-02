"""Importa y contrasta predicciones OOS con el protocolo progresivo original."""

from dataclasses import dataclass
import hashlib
import json

import numpy as np
import pandas as pd

from src.modeling.train import evaluar_fold, preparar_gold, separar_temporada, separar_anio_calendario
from src.modeling.validacion_temporal_compacta import ejecutar_validacion_temporal_compacta, variantes_compactas
from src.utils.paths import (GOLD, GOLD_MANIFEST, METRICAS_COMPACTAS, PREDICCIONES_COMPACTAS,
                             SERVING_PROTOCOLO_REGENERADO, SILVER_INTEGRADO)
from src.validation.calidad_gx import leer_gold
from src.validation.contrato_pronostico import CLAVE


@dataclass
class Protocolo:
    reporte: dict
    predicciones: pd.DataFrame
    datos: dict
    particiones: dict
    hashes: dict
    metricas_path: object
    predicciones_path: object


def cargar_protocolo(horizontes, variantes, *, metricas_path=METRICAS_COMPACTAS,
                    predicciones_path=PREDICCIONES_COMPACTAS):
    """Si falta el CSV, regenera en models/serving sin sobrescribir a Rosa."""
    if not predicciones_path.exists():
        metricas_path = SERVING_PROTOCOLO_REGENERADO / "metricas.json"
        predicciones_path = SERVING_PROTOCOLO_REGENERADO / "predicciones_por_bloque.csv"
        if not predicciones_path.exists() or not metricas_path.exists():
            print("Falta el CSV OOS: se ejecutará el protocolo existente en models/serving")
            ejecutar_validacion_temporal_compacta(salida_dir=SERVING_PROTOCOLO_REGENERADO,
                metricas_path=metricas_path)
    reporte = json.loads(metricas_path.read_text(encoding="utf-8"))
    pred = pd.read_csv(predicciones_path, dtype={"ubigeo": "string"},
                       parse_dates=["semana_inicio", "origen_cierre"])
    requeridas = {*CLAVE, "semana_inicio", "origen_cierre", "horizonte", "variante", "bloque",
                  "casos_Dengue", "brote", "umbral_brote_casos", "probabilidad_brote", "casos_predichos"}
    if not requeridas <= set(pred) or pred.duplicated([*CLAVE, "horizonte", "variante", "bloque"]).any():
        raise ValueError("El CSV OOS tiene columnas ausentes o llaves duplicadas")
    if reporte["sha256_manifest_gold"] != hashlib.sha256(GOLD_MANIFEST.read_bytes()).hexdigest():
        raise ValueError("El protocolo temporal no corresponde al manifiesto gold actual")
    datos, particiones = {}, {}
    for h in horizontes:
        gold, archivo = leer_gold(GOLD, h)
        bloque_h = reporte["horizontes"].get(str(h))
        if not bloque_h or bloque_h["sha256_gold"] != hashlib.sha256(archivo.read_bytes()).hexdigest():
            raise ValueError(f"Las métricas h={h} no corresponden al gold actual")
        datos[h], _ = preparar_gold(gold, h)
        for nombre in set(variantes.values()):
            cols = variantes_compactas(h).get(nombre)
            resultado = bloque_h["variantes"].get(nombre)
            if not resultado or cols != resultado["columnas"]:
                raise ValueError("Las columnas del protocolo no coinciden con el contrato de variantes")
            folds = [*resultado["folds"], resultado["sensibilidad_2025"]]
            for fold in folds:
                bloque = fold["bloque"]
                train, prueba, corte = (separar_anio_calendario(datos[h], 2025) if bloque == "calendario_2025"
                                        else separar_temporada(datos[h], int(bloque.split("_")[-1])))
                if str(corte.date()) != fold["corte_ajuste"] or len(train) != fold["n_entrenamiento"]:
                    raise ValueError("El corte de entrenamiento difiere del protocolo guardado")
                seleccion = pred.loc[pred.horizonte.eq(h) & pred.variante.eq(nombre) & pred.bloque.eq(bloque)]
                verificar_bloque(seleccion, prueba, fold, h, nombre)
                particiones[h, nombre, bloque] = {"inicio_entrenamiento": train.semana_inicio.min().date(),
                    "corte": corte.date(), "fold": fold}
    hashes = {"protocolo_metricas": hashlib.sha256(metricas_path.read_bytes()).hexdigest(),
              "protocolo_predicciones": hashlib.sha256(predicciones_path.read_bytes()).hexdigest()}
    return Protocolo(reporte, pred, datos, particiones, hashes, metricas_path, predicciones_path)


def verificar_bloque(pred, prueba, fold, horizonte, variante):
    """Comprueba cobertura, objetivos, origen y métricas sin cambiar sus valores."""
    if len(pred) != len(prueba) or set(map(tuple, pred[CLAVE].to_numpy())) != set(map(tuple, prueba[CLAVE].to_numpy())):
        raise ValueError(f"Las predicciones OOS no cubren el bloque {fold['bloque']}")
    columnas = ["semana_inicio", "origen_cierre", "casos_Dengue", "brote", "umbral_brote_casos"]
    p = pred.sort_values(CLAVE).reset_index(drop=True).copy()
    real = prueba.sort_values(CLAVE).reset_index(drop=True)
    for c in columnas[:2]:
        if not p[c].equals(real[c]):
            raise ValueError("Las fechas de las predicciones no coinciden con el corte temporal")
    for c in columnas[2:]:
        if not np.allclose(p[c].to_numpy(float), real[c].to_numpy(float), rtol=1e-12, atol=1e-12):
            raise ValueError("El observado o etiqueta del CSV OOS difiere de gold")
    lag = f"casos_lag_{horizonte}"
    if lag not in p or not np.array_equal(p[lag].to_numpy(float), real[lag].to_numpy(float)):
        raise ValueError("La persistencia del CSV OOS difiere del predictor de gold")
    # XGBoost exportó float32. Recuperar ese tipo reproduce el JSON de
    # evaluación; los valores originales del CSV se conservan para importar.
    for c in ("probabilidad_brote", "casos_predichos"):
        p[c] = p[c].astype("float32")
    calculado = evaluar_fold(p, horizonte=horizonte, variante=variante, bloque=fold["bloque"],
        tipo=fold["tipo"], corte=pd.Timestamp(fold["corte_ajuste"]), n_entrenamiento=fold["n_entrenamiento"],
        umbral_clasificacion=fold["clasificacion"]["umbral_probabilidad"])
    for tipo in ("clasificacion", "regresion", "persistencia"):
        _comparar_metricas(calculado[tipo], fold[tipo])


def _comparar_metricas(actual, guardado):
    for clave, esperado in guardado.items():
        if isinstance(esperado, dict):
            _comparar_metricas(actual[clave], esperado)
        elif esperado is None:
            if actual[clave] is not None:
                raise ValueError("Una métrica ausente no puede sustituirse por cero")
        elif not np.isclose(actual[clave], esperado, rtol=1e-10, atol=1e-10):
            raise ValueError(f"Las predicciones OOS no reproducen la métrica guardada: {clave}")


def metricas_de_variante(protocolo, horizonte, variante):
    """Conserva selección, contraste y sensibilidad separados, sin promediarlos."""
    resultado = protocolo.reporte["horizontes"][str(horizonte)]["variantes"][variante]
    return {"bloques": {f["bloque"]: f for f in [*resultado["folds"], resultado["sensibilidad_2025"]]},
            "procedencia": "Protocolo temporal progresivo; métricas de versiones por bloque, no del ajuste final",
            "sha256_reporte": protocolo.hashes["protocolo_metricas"],
            "sha256_predicciones": protocolo.hashes["protocolo_predicciones"],
            "device_evaluacion": protocolo.reporte["parametros"]["device"],
            "version_xgboost_evaluacion": protocolo.reporte["version_xgboost"]}
