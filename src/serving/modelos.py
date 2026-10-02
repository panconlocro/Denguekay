"""Ajuste de servicio con train.py y registro de versiones según el documento OE2.

El entrenamiento no cambia: reutiliza ``ajustar_modelos``, los hiperparámetros
base y las variantes del protocolo compacto. Aquí solo se empaqueta el
resultado (booster a Storage, metadatos a ``version_modelo``).
"""

from dataclasses import dataclass
import platform

import pandas as pd
from sqlalchemy import select
from xgboost import __version__ as XGBOOST_VERSION

from src.db.modelos import ImportanciaVariable, VersionModelo
from src.modeling.dispositivo import configuracion_xgboost
from src.modeling.train import PARAMETROS_BASE, ajustar_modelos
from src.modeling.validacion_temporal_compacta import variantes_compactas
from src.serving.artefactos import serializar_booster, sha256_bytes
from src.serving.protocolo import metricas_de_variante
from src.validation.validacion_modelo import evaluar_validacion_modelo

PREFIJOS = {"clasificacion": "clf", "regresion": "reg"}


@dataclass
class VersionPreparada:
    datos: dict
    artefacto: bytes
    importancias: list


def _particion(metricas):
    campos = ("bloque", "tipo", "corte_ajuste", "primera_semana_objetivo", "ultima_semana_objetivo",
              "n_entrenamiento", "n_prueba", "calibracion")
    return {nombre: {c: f[c] for c in campos if c in f} for nombre, f in metricas["bloques"].items()}


def entrenar_versiones_servicio(protocolo, horizontes, cfg, corte):
    """Usa todas las etiquetas cerradas al corte y las mismas funciones/hiperparámetros.

    ``ajustar_modelos`` devuelve ambos objetivos; se conserva el componente
    seleccionado por configuración, sin cambiar la lógica del entrenamiento.
    """
    versiones = {}
    for h in horizontes:
        fuente = protocolo.datos[h]
        train = fuente.loc[(fuente.semana_inicio + pd.Timedelta(days=6)).le(pd.Timestamp(corte))].copy()
        if train.empty or train.brote.nunique() != 2:
            raise ValueError("El ajuste final requiere etiquetas cerradas y ambas clases")
        pares = {nombre: ajustar_modelos(train, variantes_compactas(h)[nombre]) for nombre in set(cfg.variantes.values())}
        evaluacion = protocolo.reporte
        for tarea, nombre in cfg.variantes.items():
            modelo = pares[nombre][1 if tarea == "clasificacion" else 0]
            metricas = metricas_de_variante(protocolo, h, nombre)
            artefacto = serializar_booster(modelo)
            datos = {
                "tarea": tarea, "horizonte": h, "algoritmo": "xgboost",
                "variables": variantes_compactas(h)[nombre], "hiperparametros": dict(PARAMETROS_BASE),
                "metricas": metricas,
                "umbral_probabilidad": (metricas["bloques"]["calendario_2025"]["clasificacion"]["umbral_probabilidad"]
                                        if tarea == "clasificacion" else None),
                "sha256_dataset": evaluacion["horizontes"][str(h)]["sha256_gold"],
                "sha256_artefacto": sha256_bytes(artefacto),
                "reproducibilidad": {
                    "variante": nombre, "device": configuracion_xgboost()["device"],
                    "version_xgboost": XGBOOST_VERSION,
                    "plataforma": f"{platform.system()} {platform.release()} {platform.machine()}",
                    "entrenamiento_inicio": str(train.semana_inicio.min().date()),
                    "entrenamiento_corte": str(corte),
                    "sha256_manifiesto_gold": evaluacion["sha256_manifest_gold"],
                    "particion_temporal": {"bloques": _particion(metricas),
                                           "criterio_seleccion": evaluacion["criterio_seleccion"],
                                           "nota_2024": evaluacion["nota_2024"],
                                           "alcance": "Servicio: ajuste con etiquetas cerradas al corte"}},
            }
            ganancias = modelo.get_booster().get_score(importance_type="gain")
            importancias = [{"variable": c, "importancia": float(g), "rango": rango}
                            for rango, (c, g) in enumerate(sorted(ganancias.items(), key=lambda x: (-x[1], x[0])), 1)]
            versiones[h, tarea] = VersionPreparada(datos, artefacto, importancias)
    return versiones


def cumple_umbrales(tarea, metricas, criterios):
    """Umbrales de parametro_sistema aplicados a las métricas guardadas del bloque decisor."""
    return evaluar_validacion_modelo(tarea, metricas, criterios)["estado_validacion"] == "validado"


def siguiente_codigo(sesion, tarea, horizonte):
    prefijo = f"{PREFIJOS[tarea]}-h{horizonte}-v"
    existentes = sesion.scalars(select(VersionModelo.codigo).where(VersionModelo.codigo.like(f"{prefijo}%")))
    numeros = [int(c.removeprefix(prefijo)) for c in existentes if c.removeprefix(prefijo).isdigit()]
    return f"{prefijo}{max(numeros, default=0) + 1}"


def ruta_artefacto(almacenamiento, codigo, contenido):
    """``modelos/<codigo>.json``; nunca sobrescribe un artefacto distinto.

    Otra BD local (p. ej. la de pruebas) puede haber guardado ya ese código con
    otro booster: en ese caso se usa un nombre con el SHA-256, sin pisar el ajeno.
    """
    ruta = f"modelos/{codigo}.json"
    if almacenamiento.existe(ruta):
        if sha256_bytes(almacenamiento.leer(ruta)) == sha256_bytes(contenido):
            return ruta
        ruta = f"modelos/{codigo}-{sha256_bytes(contenido)[:12]}.json"
    if not almacenamiento.existe(ruta):
        almacenamiento.guardar(ruta, contenido)
    return ruta


def guardar_versiones(sesion, preparadas, mlflow_run_id, criterios, almacenamiento):
    """Registra cada versión como ``candidata``; un mismo artefacto reutiliza su versión.

    El booster se guarda en ``modelos/<codigo>.json`` y su hash queda en la BD.
    """
    resultado = {}
    for clave, preparada in preparadas.items():
        datos = preparada.datos
        version = sesion.scalar(select(VersionModelo).where(
            VersionModelo.tarea == datos["tarea"], VersionModelo.horizonte == datos["horizonte"],
            VersionModelo.sha256_artefacto == datos["sha256_artefacto"],
            VersionModelo.sha256_dataset == datos["sha256_dataset"]))
        if version is None:
            codigo = siguiente_codigo(sesion, datos["tarea"], datos["horizonte"])
            ruta = ruta_artefacto(almacenamiento, codigo, preparada.artefacto)
            version = VersionModelo(**datos, codigo=codigo, ruta_artefacto=ruta, estado="candidata",
                                    mlflow_run_id=mlflow_run_id,
                                    cumple_umbrales=cumple_umbrales(datos["tarea"], datos["metricas"], criterios))
            sesion.add(version)
            sesion.flush()
            for importancia in preparada.importancias:
                sesion.add(ImportanciaVariable(id_version=version.id_version, **importancia))
            sesion.flush()
        resultado[clave] = version
    return resultado


def reporte_servicio(preparadas, protocolo, corte):
    """Forma estándar para MLflow; las métricas temporales son importadas, no de este ajuste."""
    reporte = {"experimento": "versiones_de_servicio", "parametros": dict(PARAMETROS_BASE),
               "version_xgboost": XGBOOST_VERSION, "fecha_corte_datos": str(corte),
               "device_evaluacion_importada": protocolo.reporte["parametros"]["device"],
               "evaluacion_generada_en_esta_corrida": False,
               "nota_metricas": "Las métricas temporales importadas se adjuntan como evidencia histórica; no son una evaluación del ajuste final",
               "sha256_manifest_gold": protocolo.reporte["sha256_manifest_gold"], "horizontes": {}}
    for (h, tarea), preparada in preparadas.items():
        datos = preparada.datos
        bloque = reporte["horizontes"].setdefault(str(h), {
            "archivo_gold": protocolo.reporte["horizontes"][str(h)]["archivo_gold"],
            "sha256_gold": datos["sha256_dataset"], "variantes": {}})
        bloque["variantes"][f"{datos['reproducibilidad']['variante']}_{tarea}"] = {
            "columnas": datos["variables"], "tipo_modelo": tarea, "corte_ajuste_servicio": str(corte),
            "umbral_probabilidad": datos["umbral_probabilidad"], "sha256_artefacto": datos["sha256_artefacto"]}
    return reporte
