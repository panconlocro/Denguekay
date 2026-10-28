"""Service publication options read from config.yaml.

The risk cutoffs, the acceptance thresholds and the outbreak rule are not here:
they live in ``parametro_sistema`` (seeded by migration 0003_oe2).
"""

from dataclasses import dataclass

import yaml

from denguekay.config.paths import CONFIG

ALLOWED_VARIANTS = {"base_4", "base_6", "base_6_poblacion_2017"}


@dataclass(frozen=True)
class ServiceSettings:
    horizontes: tuple
    variantes: dict
    servir_no_validadas: bool
    seleccion_experimental: dict
    cors_origen: str


def service_settings(path=CONFIG):
    """Fail on unknown variants, horizons without gold or incomplete selections."""
    with open(path, encoding="utf-8") as file:
        value = (yaml.safe_load(file) or {}).get("serving")
    if not isinstance(value, dict):
        raise ValueError("Falta la sección serving en config.yaml")
    options = ServiceSettings(**{**value, "horizontes": tuple(value["horizontes"])})
    if not options.horizontes or any(h not in (2, 4) or isinstance(h, bool) for h in options.horizontes):
        raise ValueError("Los horizontes publicables son 2 y 4: solo existe gold para ellos")
    if set(options.variantes) != {"clasificacion", "regresion"} or not set(options.variantes.values()) <= ALLOWED_VARIANTS:
        raise ValueError("Las variantes deben pertenecer al protocolo compacto")
    if not isinstance(options.servir_no_validadas, bool):
        raise ValueError("servir_no_validadas debe ser un booleano")
    selection = options.seleccion_experimental
    if not isinstance(selection, dict) or any(
            not isinstance(v, dict) or set(v) != {"clasificacion", "regresion"} for v in selection.values()):
        raise ValueError("seleccion_experimental debe indicar clasificacion y regresion por horizonte")
    if any(len(code) > 20 for v in selection.values() for code in v.values()):
        raise ValueError("Los códigos de versión tienen como máximo 20 caracteres")
    return options
