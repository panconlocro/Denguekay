"""The Predictor port and the objects shared by every predictor type (decision M1).

A predictor turns ``ServingInputs`` (built from the database) into one row per district and horizon
with the columns of ``OUTPUT_COLUMNS``. Its package builder turns training data into a
``BuiltPackage`` (files, versions and OOS predictions) that publication stores generically.
"""

from dataclasses import dataclass, field
from typing import ClassVar, Protocol

import numpy as np
import pandas as pd

OUTPUT_COLUMNS = ["ubigeo", "horizonte", "probabilidad_brote", "casos_estimados",
                  "casos_intervalo_inferior", "casos_intervalo_superior", "motivo_no_disponible"]
OOS_COLUMNS = ["horizonte", "bloque", "ubigeo", "anio", "semana", "origen_cierre",
               "probabilidad_brote", "casos_estimados"]


class InferenceUnavailable(ValueError):
    """The request cannot be served with the data or models in the database (HTTP 409)."""


class Predictor(Protocol):
    """Port that serving.inference uses; the API never imports a concrete predictor."""

    kind: ClassVar[str]
    required_inputs: ClassVar[frozenset]
    horizons: tuple
    interval_level: float | None  # nominal probability of its case intervals; None if it gives none

    @classmethod
    def from_package(cls, package): ...

    def predict(self, inputs, cutoff, horizons) -> pd.DataFrame: ...


@dataclass
class VersionSpec:
    """One ``version_modelo`` row of a package: a task and a horizon."""
    tarea: str
    horizonte: int
    code_prefix: str  # e.g. "clf-h2-v"; the number is the next free one in the database
    data: dict  # algoritmo, variables, hiperparametros, metricas, umbral_probabilidad, sha256_dataset, reproducibilidad
    importances: list = field(default_factory=list)


@dataclass
class BuiltPackage:
    """What a package builder hands to publication; nothing here depends on the database."""
    kind: str
    code: str
    horizons: tuple
    files: dict  # name -> bytes
    variables: dict  # str(horizon) -> {task: [columns]}
    interval_level: float | None
    options: dict
    versions: list  # VersionSpec
    oos: pd.DataFrame | None  # OOS_COLUMNS
    oos_detail: dict
    report: dict  # MLflow report (standard shape of denguekay.model.tracking)
    fingerprint: str | None = None  # behavioural fingerprint of a frozen configuration, if any


def validate_output(output, horizons, interval_level):
    """Shape and ranges of a predictor's output; a violation is a bug of the predictor, not a 409."""
    if list(output.columns) != OUTPUT_COLUMNS:
        raise ValueError(f"La salida del predictor debe tener las columnas {OUTPUT_COLUMNS}")
    if output.duplicated(["ubigeo", "horizonte"]).any() or not output.horizonte.isin(horizons).all():
        raise ValueError("La salida del predictor repite distritos o trae horizontes no pedidos")
    available = output.motivo_no_disponible.isna()
    values = output.loc[available, ["probabilidad_brote", "casos_estimados"]].to_numpy(float)
    if not np.isfinite(values).all() or (values[:, 0] < 0).any() or (values[:, 0] > 1).any() or (values[:, 1] < 0).any():
        raise ValueError("El predictor produjo probabilidades o casos inválidos")
    low, high = output.casos_intervalo_inferior, output.casos_intervalo_superior
    if not low.isna().eq(high.isna()).all() or (low.notna() & ~available).any():
        raise ValueError("Los límites del intervalo deben venir juntos y solo en predicciones disponibles")
    if low.notna().any():
        if interval_level is None:
            raise ValueError("El predictor dio intervalos sin declarar su nivel")
        bounds = output.loc[low.notna(), ["casos_intervalo_inferior", "casos_intervalo_superior"]].to_numpy(float)
        if not np.isfinite(bounds).all() or (bounds[:, 0] < 0).any() or (bounds[:, 0] > bounds[:, 1]).any():
            raise ValueError("El predictor produjo un intervalo de casos inválido")
    return output
