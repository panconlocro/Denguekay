"""Subconjuntos trazables de gold y predicciones reales para probar inferencia."""

from datetime import date
import hashlib
import json

import pandas as pd

from src.modeling.inferencia_futura import construir_filas_futuras
from src.serving.configuracion import configuracion_servicio
from src.serving.modelos import entrenar_versiones_servicio, versiones_historicas
from src.serving.protocolo import Protocolo
from src.utils.paths import BACKEND_FIXTURES


def leer_csv(nombre):
    datos = pd.read_csv(BACKEND_FIXTURES / nombre, dtype={"ubigeo": "string"})
    for c in ("semana_inicio", "origen_inicio", "origen_cierre"):
        if c in datos:
            datos[c] = pd.to_datetime(datos[c])
    return datos


def protocolo_muestra():
    """Conserva métricas de Rosa; el entrenamiento de prueba usa gold reducido."""
    reporte = json.loads((BACKEND_FIXTURES / "protocolo_muestra.json").read_text(encoding="utf-8"))
    datos = {h: leer_csv(f"entrenamiento_h{h}_muestra.csv") for h in (2, 4)}
    particiones = {}
    for h in (2, 4):
        for nombre, variante in reporte["horizontes"][str(h)]["variantes"].items():
            for f in [*variante["folds"], variante["sensibilidad_2025"]]:
                particiones[h, nombre, f["bloque"]] = {
                    "inicio_entrenamiento": date(2017, 1, 1),
                    "corte": date.fromisoformat(f["corte_ajuste"]), "fold": f}
    hashes = {"protocolo_metricas": hashlib.sha256((BACKEND_FIXTURES / "protocolo_muestra.json").read_bytes()).hexdigest(),
              "protocolo_predicciones": hashlib.sha256((BACKEND_FIXTURES / "retrospectivas_muestra.csv").read_bytes()).hexdigest()}
    return Protocolo(reporte, leer_csv("retrospectivas_muestra.csv"), datos, particiones,
                     hashes, BACKEND_FIXTURES / "protocolo_muestra.json",
                     BACKEND_FIXTURES / "retrospectivas_muestra.csv")


def preparar_muestra():
    """Entrena XGBoost real; no emplea dobles ni probabilidades prefijadas."""
    protocolo = protocolo_muestra()
    cfg = configuracion_servicio()
    referencia = leer_csv("referencia_2017_muestra.csv")
    futuros = {h: construir_filas_futuras(leer_csv(f"gold_temporal_h{h}_muestra.csv"), h,
                                        referencia=referencia)[0] for h in (2, 4)}
    versiones = entrenar_versiones_servicio(protocolo, (2, 4), cfg, date(2025, 12, 27))
    # El booster de prueba se ajustó sobre estos archivos, no sobre gold completo.
    from src.serving.artefactos import huella_json
    for (h, tipo, bloque), preparada in versiones.items():
        preparada.datos["sha256_gold"] = hashlib.sha256(
            (BACKEND_FIXTURES / f"entrenamiento_h{h}_muestra.csv").read_bytes()).hexdigest()
        preparada.datos["huella"] = huella_json({**preparada.datos, "alcance": "Prueba con subconjunto real"})
    versiones.update(versiones_historicas(protocolo, (2, 4), cfg))
    return cfg, protocolo, futuros, versiones
