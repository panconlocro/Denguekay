"""Opciones de publicación y política de disponibilidad del servicio."""

from dataclasses import dataclass
import math

import yaml

from src.utils.paths import CONFIG


@dataclass(frozen=True)
class ConfiguracionServicio:
    horizontes: tuple
    variantes: dict
    riesgo: dict
    alerta_nivel_minimo: str
    servir_no_validadas: bool
    cors_origen: str
    criterios_validacion: dict


def configuracion_servicio(ruta=CONFIG):
    """Falla ante variantes desconocidas o cortes de probabilidad inválidos."""
    with open(ruta, encoding="utf-8") as archivo:
        valor = (yaml.safe_load(archivo) or {}).get("serving")
    if not isinstance(valor, dict):
        raise ValueError("Falta la sección serving en config.yaml")
    opciones = ConfiguracionServicio(**{**valor, "horizontes": tuple(valor["horizontes"])})
    if not opciones.horizontes or any(h not in (2, 3, 4) or isinstance(h, bool) for h in opciones.horizontes):
        raise ValueError("Los horizontes configurables son 2, 3 y 4; requieren gold correspondiente")
    nombres = {"base_4", "base_6", "base_6_poblacion_2017"}
    if set(opciones.variantes) != {"clasificacion", "regresion"} or not set(opciones.variantes.values()) <= nombres:
        raise ValueError("Las variantes deben pertenecer al protocolo compacto")
    cortes = [opciones.riesgo.get(k) for k in ("medio", "alto", "muy_alto")]
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in cortes) or not 0 < cortes[0] < cortes[1] < cortes[2] < 1:
        raise ValueError("Los umbrales de riesgo deben ser crecientes y estar entre 0 y 1")
    if opciones.alerta_nivel_minimo not in ("Alto", "Muy alto"):
        raise ValueError("La alerta visible comienza en Alto o Muy alto")
    if not isinstance(opciones.servir_no_validadas, bool):
        raise ValueError("servir_no_validadas debe ser un booleano")
    c = opciones.criterios_validacion
    if not isinstance(c.get("bloques"), list) or not c["bloques"]:
        raise ValueError("Faltan los bloques para verificar la aceptación del modelo")
    for clave in ("recall_minimo", "precision_minima", "f1_minimo", "proporcion_error_persistencia"):
        limite = c.get(clave)
        if not isinstance(limite, (int, float)) or isinstance(limite, bool) or not math.isfinite(limite) or not 0 < limite <= 1:
            raise ValueError(f"Criterio de validación inválido: {clave}")
    return opciones
