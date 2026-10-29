"""Pluggable prediction engine: registry of predictor types (decision M1 of docs/backend/api_v1_decisiones.md).

Each type is a module with a ``Predictor`` class (the port in ``base``) and the functions that build its
package (``validate``, ``prepare``, ``build``, ``fingerprint_parameters``). A new model adds a module and
an entry in ``PREDICTORS``; serving.inference, publication and the API do not change.
"""

from collections import OrderedDict
from importlib import import_module

from denguekay.serving.artifacts import InvalidArtifact

PREDICTORS = {"v0_compact_xgb": "denguekay.serving.predictors.v0_compact_xgb"}
_CACHE = OrderedDict()
_CACHE_SIZE = 8


def predictor_module(kind):
    """Module of a registered type; imported only when it is used (the API imports no concrete predictor)."""
    if kind not in PREDICTORS:
        raise InvalidArtifact(f"Tipo de predictor desconocido: {kind}")
    return import_module(PREDICTORS[kind])


def load_predictor(package):
    """Predictor of a verified package, cached by the manifest's SHA-256 (same hash = same files)."""
    predictor = _CACHE.get(package.sha256)
    if predictor is None:
        predictor = predictor_module(package.kind).Predictor.from_package(package)
        _CACHE[package.sha256] = predictor
        while len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
    else:
        _CACHE.move_to_end(package.sha256)
    return predictor
