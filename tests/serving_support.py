"""Subconjuntos trazables de gold y predicciones reales para probar inferencia."""

from datetime import date
import hashlib
import json

from backend_support import leer_csv
from denguekay.serving.settings import ServiceSettings
from denguekay.serving.predictors import v0_compact_xgb as v0
from denguekay.serving.protocol import Protocol
from denguekay.config.paths import BACKEND_FIXTURES

CORTE = date(2025, 12, 27)
# La v0 de las pruebas fija su configuración y su selección aquí: config.yaml ya publica la v2 y la
# selección experimental la fija la publicación, no load_data (fase 4).
V0_PAQUETE = {"tipo": "v0_compact_xgb", "horizontes": [2, 4],
              "opciones": {"variantes": {"clasificacion": "base_6_poblacion_2017", "regresion": "base_6"}}}
V0_SELECCION = {2: {"clasificacion": "clf-h2-v1", "regresion": "reg-h2-v1"},
                4: {"clasificacion": "clf-h4-v1", "regresion": "reg-h4-v1"}}


def configuracion_v0():
    """Opciones de servicio con el paquete v0 de las pruebas."""
    return ServiceSettings(paquete=V0_PAQUETE, servir_no_validadas=True, cors_origenes=["http://localhost:5173"])


def fijar_seleccion(motor, seleccion=None):
    """Selección experimental en la BD temporal (la de la v0 por defecto), como haría publish."""
    from denguekay.db.session import transaction
    from denguekay.serving.parameters import set_experimental_selection

    with transaction(motor) as sesion:
        return set_experimental_selection(sesion, V0_SELECCION if seleccion is None else seleccion)


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
    return Protocol(reporte, leer_csv("retrospectivas_muestra.csv"), datos, particiones,
                     hashes, BACKEND_FIXTURES / "protocolo_muestra.json",
                     BACKEND_FIXTURES / "retrospectivas_muestra.csv")


def preparar_muestra():
    """Entrena XGBoost real sobre filas reales de gold; no usa dobles ni probabilidades fijas."""
    protocolo = protocolo_muestra()
    cfg = configuracion_v0()
    preparadas = v0.train_service_versions(protocolo, (2, 4), cfg.opciones["variantes"], CORTE)
    # El booster de prueba se ajustó sobre estos archivos, no sobre gold completo.
    for (h, _), preparada in preparadas.items():
        preparada.data["sha256_dataset"] = hashlib.sha256(
            (BACKEND_FIXTURES / f"entrenamiento_h{h}_muestra.csv").read_bytes()).hexdigest()
    return cfg, protocolo, preparadas


def sample_package(cfg, protocol, trained):
    """v0 package (four boosters, versions and OOS) of the boosters trained on the fixtures."""
    return v0.build(v0.Prepared(protocol, dict(protocol.hashes)), (2, 4), cfg.opciones, CORTE, trained=trained)


def publish_sample(engine, load, cfg, protocol, trained, storage, run_id, fingerprint):
    """Full publication of the fixtures with the current inference (like ``publish --inferir``).

    The v0 selection is set first, as load_data seeded it before the publication until phase 4.
    """
    from denguekay.serving.publish import publish_to_db

    fijar_seleccion(engine)
    return publish_to_db(engine, load, sample_package(cfg, protocol, trained), run_id, fingerprint, storage, 0,
                         servir_no_validadas=cfg.servir_no_validadas, run_inference=True)
