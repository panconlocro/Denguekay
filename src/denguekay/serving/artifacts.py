"""Boosters in Storage: serialisation, hash check and inference."""

from functools import lru_cache
import hashlib
import json

import numpy as np
import pandas as pd
import xgboost as xgb

from denguekay.model.train import counts_from_log1p


class InvalidArtifact(ValueError):
    """The artifact is missing, does not match its hash or does not belong to the version (HTTP 409)."""


def json_fingerprint(value):
    """Reproducible identity of serialisable parameters and inputs."""
    content = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False, default=str)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def serialize_booster(model):
    """JSON bytes of the real XGBoost booster, as stored in Storage."""
    return bytes(model.get_booster().save_raw(raw_format="json"))


@lru_cache(maxsize=8)
def _load_booster(sha256, content):
    try:
        booster = xgb.Booster()
        booster.load_model(bytearray(content))
    except (ValueError, xgb.core.XGBoostError) as error:
        raise InvalidArtifact("El artefacto XGBoost guardado no se puede cargar") from error
    # The API may run on CPU even if the version was trained on GPU.
    booster.set_param({"device": "cpu", "nthread": 1})
    return booster


def load_booster(version, storage):
    """Read the artifact from Storage and check its SHA-256 against the database."""
    try:
        content = storage.read(version.ruta_artefacto)
    except (FileNotFoundError, ValueError) as error:
        raise InvalidArtifact(f"No se encontró el artefacto de {version.codigo}") from error
    if sha256_bytes(content) != version.sha256_artefacto:
        raise InvalidArtifact(f"El artefacto de {version.codigo} no coincide con su SHA-256 registrado")
    return _load_booster(version.sha256_artefacto, content)


def predict_with_version(version, vectors, storage):
    """Evaluate exactly the columns saved in the version, in their order."""
    columns = list(version.variables or [])
    data = pd.DataFrame(vectors)
    if not columns or len(columns) != len(set(columns)):
        raise InvalidArtifact("La versión no contiene un esquema de variables válido")
    if not set(columns) <= set(data):
        raise ValueError("El vector no contiene todas las variables de la versión")
    x = data[columns].astype(float)
    if x.isna().any().any() or not np.isfinite(x.to_numpy()).all():
        raise ValueError("El vector contiene valores faltantes o no finitos")
    booster = load_booster(version, storage)
    if booster.feature_names != columns:
        raise InvalidArtifact("Las columnas del booster no coinciden con la versión")
    output = booster.predict(xgb.DMatrix(x))
    if not np.isfinite(output).all():
        raise ValueError("El modelo produjo una predicción no finita")
    if version.tarea == "regresion":
        return counts_from_log1p(output)
    if ((output < 0) | (output > 1)).any():
        raise ValueError("El clasificador produjo probabilidades inválidas")
    return output
