"""Inferencia desde el JSON del booster, sin leer gold ni archivos de modelos."""

from functools import lru_cache
import hashlib
import json

import numpy as np
import pandas as pd
import xgboost as xgb

from src.modeling.train import conteos_desde_log1p


def huella_json(valor):
    """Identidad reproducible de parámetros y entradas serializables."""
    contenido = json.dumps(valor, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False, default=str)
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def serializar_booster(modelo):
    """Conserva el booster XGBoost real como un objeto JSON en la BD."""
    return json.loads(modelo.get_booster().save_raw(raw_format="json"))


@lru_cache(maxsize=8)
def _cargar_booster(contenido):
    booster = xgb.Booster()
    booster.load_model(bytearray(contenido.encode("utf-8")))
    # La API puede correr en CPU aunque la versión haya sido entrenada en GPU.
    booster.set_param({"device": "cpu", "nthread": 1})
    return booster


def predecir_con_version(version, vectores):
    """Reevalúa exactamente las columnas guardadas en la versión, en su orden.

    El consumidor pasa una versión ORM cargada de la BD y sus vectores. Los
    modelos históricos sin booster no se sustituyen por el modelo vigente.
    """
    if version.artefacto is None:
        raise ValueError("La versión histórica no tiene artefacto para recalcular")
    datos = pd.DataFrame(vectores)
    if not version.columnas or len(version.columnas) != len(set(version.columnas)):
        raise ValueError("La versión no contiene un esquema de columnas válido")
    if not set(version.columnas) <= set(datos):
        raise ValueError("El vector no contiene todas las variables de la versión")
    x = datos[version.columnas].astype(float)
    if x.isna().any().any() or not np.isfinite(x.to_numpy()).all():
        raise ValueError("El vector contiene valores faltantes o no finitos")
    if version.tipo == "persistencia":
        if version.artefacto.get("columna") != version.columnas[0] or len(version.columnas) != 1:
            raise ValueError("El artefacto de persistencia no coincide con su esquema")
        valores = x.iloc[:, 0].to_numpy()
        if (valores < 0).any():
            raise ValueError("La persistencia no admite casos negativos")
        return valores
    if version.tipo not in {"clasificacion", "regresion"}:
        raise ValueError("Tipo de modelo no admitido para inferencia")
    contenido = json.dumps(version.artefacto, separators=(",", ":"), allow_nan=False)
    booster = _cargar_booster(contenido)
    if booster.feature_names != version.columnas:
        raise ValueError("Las columnas del booster no coinciden con la versión")
    salida = booster.predict(xgb.DMatrix(x))
    if not np.isfinite(salida).all():
        raise ValueError("El modelo produjo una predicción no finita")
    if version.tipo == "regresion":
        return conteos_desde_log1p(salida)
    if ((salida < 0) | (salida > 1)).any():
        raise ValueError("El clasificador produjo probabilidades inválidas")
    return salida
