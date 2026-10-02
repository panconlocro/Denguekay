"""Subconjuntos trazables de gold y predicciones reales para probar inferencia."""

from datetime import date
import hashlib
import json

from backend_soporte import leer_csv
from src.serving.configuracion import configuracion_servicio
from src.serving.modelos import entrenar_versiones_servicio
from src.serving.protocolo import Protocolo
from src.utils.paths import BACKEND_FIXTURES

CORTE = date(2025, 12, 27)


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
    """Entrena XGBoost real sobre filas reales de gold; no usa dobles ni probabilidades fijas."""
    protocolo = protocolo_muestra()
    cfg = configuracion_servicio()
    preparadas = entrenar_versiones_servicio(protocolo, (2, 4), cfg, CORTE)
    # El booster de prueba se ajustó sobre estos archivos, no sobre gold completo.
    for (h, _), preparada in preparadas.items():
        preparada.datos["sha256_dataset"] = hashlib.sha256(
            (BACKEND_FIXTURES / f"entrenamiento_h{h}_muestra.csv").read_bytes()).hexdigest()
    return cfg, protocolo, preparadas
