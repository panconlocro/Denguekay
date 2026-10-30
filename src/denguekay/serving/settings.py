"""Service publication options read from config.yaml.

``serving.paquete`` names the predictor type that publication builds (``tipo``), its horizons and the
type's own options; each type validates its options (``denguekay.serving.predictors``). The risk cutoffs,
the acceptance thresholds, the outbreak rule and the interval level are not here: they live in
``parametro_sistema`` (seeded by the migrations).
"""

from dataclasses import dataclass

import yaml

from denguekay.config.paths import CONFIG
from denguekay.serving.predictors import PREDICTORS

HORIZONS = (2, 3, 4)  # admitted by the DDL CHECK


@dataclass(frozen=True)
class ServiceSettings:
    paquete: dict
    servir_no_validadas: bool
    cors_origen: str

    @property
    def tipo_paquete(self):
        return self.paquete["tipo"]

    @property
    def horizontes(self):
        return tuple(self.paquete["horizontes"])

    @property
    def opciones(self):
        return self.paquete.get("opciones") or {}


def service_settings(path=CONFIG):
    """Fail on an unknown predictor type, horizons outside the DDL or incomplete selections."""
    with open(path, encoding="utf-8") as file:
        value = (yaml.safe_load(file) or {}).get("serving")
    if not isinstance(value, dict):
        raise ValueError("Falta la sección serving en config.yaml")
    options = ServiceSettings(**value)
    package = options.paquete
    if not isinstance(package, dict) or package.get("tipo") not in PREDICTORS:
        raise ValueError(f"serving.paquete.tipo debe ser uno de {sorted(PREDICTORS)}")
    horizons = package.get("horizontes")
    if (not isinstance(horizons, list) or not horizons or len(set(horizons)) != len(horizons)
            or any(h not in HORIZONS or isinstance(h, bool) for h in horizons)):
        raise ValueError("serving.paquete.horizontes debe listar horizontes únicos entre 2 y 4")
    if not isinstance(package.get("opciones", {}), dict):
        raise ValueError("serving.paquete.opciones debe ser un diccionario")
    if not isinstance(options.servir_no_validadas, bool):
        raise ValueError("servir_no_validadas debe ser un booleano")
    return options
