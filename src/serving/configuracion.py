"""Opciones de publicación del servicio leídas de config.yaml.

Los cortes de riesgo, los umbrales de aceptación y la regla de brote no están
aquí: viven en ``parametro_sistema`` (los siembra la migración 0003_oe2).
"""

from dataclasses import dataclass

import yaml

from src.utils.paths import CONFIG

VARIANTES_PERMITIDAS = {"base_4", "base_6", "base_6_poblacion_2017"}


@dataclass(frozen=True)
class ConfiguracionServicio:
    horizontes: tuple
    variantes: dict
    servir_no_validadas: bool
    seleccion_experimental: dict
    cors_origen: str


def configuracion_servicio(ruta=CONFIG):
    """Falla ante variantes desconocidas, horizontes sin gold o selecciones incompletas."""
    with open(ruta, encoding="utf-8") as archivo:
        valor = (yaml.safe_load(archivo) or {}).get("serving")
    if not isinstance(valor, dict):
        raise ValueError("Falta la sección serving en config.yaml")
    opciones = ConfiguracionServicio(**{**valor, "horizontes": tuple(valor["horizontes"])})
    if not opciones.horizontes or any(h not in (2, 4) or isinstance(h, bool) for h in opciones.horizontes):
        raise ValueError("Los horizontes publicables son 2 y 4: solo existe gold para ellos")
    if set(opciones.variantes) != {"clasificacion", "regresion"} or not set(opciones.variantes.values()) <= VARIANTES_PERMITIDAS:
        raise ValueError("Las variantes deben pertenecer al protocolo compacto")
    if not isinstance(opciones.servir_no_validadas, bool):
        raise ValueError("servir_no_validadas debe ser un booleano")
    seleccion = opciones.seleccion_experimental
    if not isinstance(seleccion, dict) or any(
            not isinstance(v, dict) or set(v) != {"clasificacion", "regresion"} for v in seleccion.values()):
        raise ValueError("seleccion_experimental debe indicar clasificacion y regresion por horizonte")
    if any(len(codigo) > 20 for v in seleccion.values() for codigo in v.values()):
        raise ValueError("Los códigos de versión tienen como máximo 20 caracteres")
    return opciones
