"""Hashes of artifacts and the error for an artifact that cannot be trusted.

Packages (manifest + files) live in ``denguekay.serving.package``; loading a type's files (for
instance XGBoost boosters) belongs to its predictor in ``denguekay.serving.predictors``.
"""

import hashlib
import json


class InvalidArtifact(ValueError):
    """The artifact is missing, does not match its hash or does not belong to the version (HTTP 409)."""


def json_fingerprint(value):
    """Reproducible identity of serialisable parameters and inputs."""
    content = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False, default=str)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()
