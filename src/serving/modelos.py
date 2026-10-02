"""Ajuste final reutilizando train.py y metadatos de versiones auditables."""

from dataclasses import dataclass
import platform

import pandas as pd
from xgboost import __version__ as XGBOOST_VERSION

from src.db.modelos import VersionModelo
from src.modeling.dispositivo import configuracion_xgboost
from src.modeling.train import PARAMETROS_BASE, ajustar_modelos
from src.modeling.validacion_temporal_compacta import variantes_compactas
from src.serving.artefactos import huella_json, serializar_booster
from src.serving.protocolo import metricas_de_variante


@dataclass
class VersionPreparada:
    datos: dict
    importancias: list


def _particion(metricas):
    campos = ("bloque", "tipo", "corte_ajuste", "primera_semana_objetivo", "ultima_semana_objetivo",
              "n_entrenamiento", "n_prueba", "calibracion")
    return {nombre: {c: f[c] for c in campos if c in f} for nombre, f in metricas["bloques"].items()}


def _metadatos(protocolo, h, tipo, nombre, cfg, origen, corte, inicio, bloque=None):
    metricas = metricas_de_variante(protocolo, h, nombre)
    evaluacion = protocolo.reporte
    columnas = [f"casos_lag_{h}"] if tipo == "persistencia" else variantes_compactas(h)[nombre]
    ultimo_fold = metricas["bloques"][bloque or "calendario_2025"]
    datos = {"horizonte": h, "tipo": tipo, "variante": "persistencia" if tipo == "persistencia" else nombre,
             "origen": origen, "bloque": bloque, "columnas": columnas,
             "hiperparametros": {} if tipo == "persistencia" else dict(PARAMETROS_BASE if origen == "servicio" else evaluacion["parametros"]),
             "umbral_probabilidad": ultimo_fold["clasificacion"]["umbral_probabilidad"] if tipo == "clasificacion" else None,
             "entrenamiento_inicio": inicio, "entrenamiento_corte": corte,
             "metricas_evaluacion": metricas, "criterios_validacion": cfg.criterios_validacion,
             "particion_temporal": {"bloques": _particion(metricas),
                 "criterio_seleccion": evaluacion["criterio_seleccion"], "nota_2024": evaluacion["nota_2024"],
                 "alcance": "Servicio: ajuste con etiquetas cerradas al origen" if origen == "servicio" else "Versión del bloque OOS importado"},
             "mlflow_run_id": None, "sha256_gold": evaluacion["horizontes"][str(h)]["sha256_gold"],
             "sha256_manifiesto": evaluacion["sha256_manifest_gold"],
             "device": configuracion_xgboost()["device"] if origen == "servicio" else evaluacion["parametros"]["device"],
             "version_xgboost": XGBOOST_VERSION if origen == "servicio" else evaluacion["version_xgboost"],
             "plataforma": f"{platform.system()} {platform.release()} {platform.machine()}" if origen == "servicio" else None,
             "activa": False, "artefacto": None, "motivo_artefacto": None}
    datos["huella"] = huella_json({k: v for k, v in datos.items() if k not in ("artefacto", "mlflow_run_id")})
    return datos


def entrenar_versiones_servicio(protocolo, horizontes, cfg, corte):
    """Usa todas las etiquetas cerradas y las mismas funciones/hiperparámetros.

    Ajusta las matrices elegidas mediante ``ajustar_modelos``. Ese helper
    devuelve ambos objetivos; se conserva el componente seleccionado por
    configuración, sin cambiar la lógica del entrenamiento documentado.
    """
    versiones = {}
    for h in horizontes:
        fuente = protocolo.datos[h]
        train = fuente.loc[(fuente.semana_inicio + pd.Timedelta(days=6)).le(pd.Timestamp(corte))].copy()
        if train.empty or train.brote.nunique() != 2:
            raise ValueError("El ajuste final requiere etiquetas cerradas y ambas clases")
        pares = {nombre: ajustar_modelos(train, variantes_compactas(h)[nombre]) for nombre in set(cfg.variantes.values())}
        for tipo, nombre in cfg.variantes.items():
            modelo = pares[nombre][1 if tipo == "clasificacion" else 0]
            valores = _metadatos(protocolo, h, tipo, nombre, cfg, "servicio", corte, train.semana_inicio.min().date())
            valores["artefacto"] = serializar_booster(modelo)
            valores["huella"] = huella_json({**{k: v for k, v in valores.items() if k not in ("artefacto", "mlflow_run_id", "huella")},
                                             "sha256_artefacto": huella_json(valores["artefacto"])})
            ganancias = modelo.get_booster().get_score(importance_type="gain")
            importancias = [{"variable": c, "importancia": float(g), "rango": rango}
                for rango, (c, g) in enumerate(sorted(ganancias.items(), key=lambda x: (-x[1], x[0])), 1)]
            versiones[h, tipo, "servicio"] = VersionPreparada(valores, importancias)
        valores = _metadatos(protocolo, h, "persistencia", cfg.variantes["regresion"], cfg,
                             "servicio", corte, train.semana_inicio.min().date())
        valores["artefacto"] = {"tipo": "persistencia", "columna": f"casos_lag_{h}",
                                 "regla": "Conteo observado en t-h, sin ajuste de parámetros"}
        versiones[h, "persistencia", "servicio"] = VersionPreparada(valores, [])
    return versiones


def versiones_historicas(protocolo, horizontes, cfg):
    """Metadatos del CSV de Rosa, sin atribuirle el booster final ni otro run."""
    versiones = {}
    for h in horizontes:
        for tipo in ("clasificacion", "regresion", "persistencia"):
            nombre = cfg.variantes["regresion" if tipo == "persistencia" else tipo]
            metricas = metricas_de_variante(protocolo, h, nombre)
            for bloque in metricas["bloques"]:
                particion = protocolo.particiones[h, nombre, bloque]
                valores = _metadatos(protocolo, h, tipo, nombre, cfg, "retrospectiva",
                                     particion["corte"], particion["inicio_entrenamiento"], bloque)
                if tipo == "persistencia":
                    valores["artefacto"] = {"tipo": "persistencia", "columna": f"casos_lag_{h}",
                                             "regla": "Conteo de referencia del bloque OOS"}
                else:
                    valores["motivo_artefacto"] = "El protocolo original guardó predicciones, pero no el booster de este bloque"
                versiones[h, tipo, bloque] = VersionPreparada(valores, [])
    return versiones


def reporte_servicio(versiones, protocolo, futuros, corte):
    """Forma estándar para MLflow; no registra folds importados como nuevos fits."""
    reporte = {"experimento": "versiones_de_servicio", "parametros": dict(PARAMETROS_BASE),
               "version_xgboost": XGBOOST_VERSION, "fecha_corte_datos": str(corte),
               "device_evaluacion_importada": protocolo.reporte["parametros"]["device"],
               "evaluacion_generada_en_esta_corrida": False,
               "nota_metricas": "Las métricas temporales importadas se adjuntan como evidencia histórica; no son una evaluación del ajuste final",
               "sha256_manifest_gold": protocolo.reporte["sha256_manifest_gold"], "horizontes": {}}
    for (h, tipo, bloque), version in versiones.items():
        if bloque != "servicio":
            continue
        valores = version.datos
        bloque_h = reporte["horizontes"].setdefault(str(h), {"archivo_gold": protocolo.reporte["horizontes"][str(h)]["archivo_gold"],
            "sha256_gold": valores["sha256_gold"], "variantes": {}})
        bloque_h["variantes"][f"{valores['variante']}_{tipo}"] = {"columnas": valores["columnas"],
            "tipo_modelo": tipo, "corte_ajuste_servicio": str(corte), "filas_futuras": len(futuros[h]),
            "umbral_probabilidad": valores["umbral_probabilidad"], "huella_version": valores["huella"],
            "estado_validacion": VersionModelo(**valores).estado_validacion}
    return reporte
