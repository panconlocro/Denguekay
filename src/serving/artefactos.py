"""Boosters en Storage: serialización, verificación de hash e inferencia."""

from functools import lru_cache
import hashlib
import json

import numpy as np
import pandas as pd
import xgboost as xgb

from src.modeling.train import conteos_desde_log1p


class ArtefactoInvalido(ValueError):
    """El artefacto falta, no coincide con su hash o no corresponde a la versión (HTTP 409)."""


def huella_json(valor):
    """Identidad reproducible de parámetros y entradas serializables."""
    contenido = json.dumps(valor, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False, default=str)
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def sha256_bytes(contenido):
    return hashlib.sha256(contenido).hexdigest()


def serializar_booster(modelo):
    """Bytes JSON del booster XGBoost real, tal como se guardan en Storage."""
    return bytes(modelo.get_booster().save_raw(raw_format="json"))


@lru_cache(maxsize=8)
def _cargar_booster(sha256, contenido):
    try:
        booster = xgb.Booster()
        booster.load_model(bytearray(contenido))
    except (ValueError, xgb.core.XGBoostError) as error:
        raise ArtefactoInvalido("El artefacto XGBoost guardado no se puede cargar") from error
    # La API puede correr en CPU aunque la versión haya sido entrenada en GPU.
    booster.set_param({"device": "cpu", "nthread": 1})
    return booster


def cargar_booster(version, almacenamiento):
    """Lee el artefacto de Storage y verifica su SHA-256 contra la BD."""
    try:
        contenido = almacenamiento.leer(version.ruta_artefacto)
    except (FileNotFoundError, ValueError) as error:
        raise ArtefactoInvalido(f"No se encontró el artefacto de {version.codigo}") from error
    if sha256_bytes(contenido) != version.sha256_artefacto:
        raise ArtefactoInvalido(f"El artefacto de {version.codigo} no coincide con su SHA-256 registrado")
    return _cargar_booster(version.sha256_artefacto, contenido)


def predecir_con_version(version, vectores, almacenamiento):
    """Evalúa exactamente las columnas guardadas en la versión, en su orden."""
    columnas = list(version.variables or [])
    datos = pd.DataFrame(vectores)
    if not columnas or len(columnas) != len(set(columnas)):
        raise ArtefactoInvalido("La versión no contiene un esquema de variables válido")
    if not set(columnas) <= set(datos):
        raise ValueError("El vector no contiene todas las variables de la versión")
    x = datos[columnas].astype(float)
    if x.isna().any().any() or not np.isfinite(x.to_numpy()).all():
        raise ValueError("El vector contiene valores faltantes o no finitos")
    booster = cargar_booster(version, almacenamiento)
    if booster.feature_names != columnas:
        raise ArtefactoInvalido("Las columnas del booster no coinciden con la versión")
    salida = booster.predict(xgb.DMatrix(x))
    if not np.isfinite(salida).all():
        raise ValueError("El modelo produjo una predicción no finita")
    if version.tarea == "regresion":
        return conteos_desde_log1p(salida)
    if ((salida < 0) | (salida > 1)).any():
        raise ValueError("El clasificador produjo probabilidades inválidas")
    return salida
