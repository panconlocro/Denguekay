"""Versions of the public contract and of the application (decision C5 of docs/backend/api_v1_decisiones.md).

The contract follows semver (docs/backend/contrato_api.md): an additive change raises the minor
version; a breaking change is not allowed under /api/v1.
"""

CONTRACT_VERSION = "1.1.0"
CONTRACT_HEADER = "X-Version-Contrato"
APP_VERSION = "2.0.0"
# Horizons admitted by the DDL CHECK; which of them have a model is read from the database.
HORIZONS = (2, 3, 4)


def no_model_reason(horizon):
    return f"sin modelo para h={horizon}"
