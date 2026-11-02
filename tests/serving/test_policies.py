"""Riesgo, aceptación, configuración, parámetros de la BD y almacenamiento local."""

from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest

import yaml

from backend_support import motor_temporal
from serving_support import protocolo_muestra
from denguekay.db.models import SystemParameter
from denguekay.db.session import transaction
from denguekay.serving import parameters as parametros
from denguekay.serving.storage import LocalStorage, validate_path
from denguekay.serving.settings import service_settings
from denguekay.serving.protocol import _compare_metrics, variant_metrics
from denguekay.serving.risk import LABELS, alert_change, risk_level
from denguekay.evaluation.acceptance import evaluate_model_validation

CORTES = {"medio": 0.25, "alto": 0.50, "muy_alto": 0.75}
CRITERIOS = {"bloques": ["temporada_2024"], "recall_minimo": 0.8, "precision_minima": 0.6,
             "f1_minimo": 0.7, "proporcion_error_persistencia": 0.85}


class TestPoliticasServicio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = service_settings()
        cls.metricas = variant_metrics(protocolo_muestra(), 2, "base_6_poblacion_2017")

    def test_bordes_de_riesgo(self):
        for p, nivel in ((None, None), (0, "bajo"), (.249999, "bajo"), (.25, "medio"), (.499999, "medio"),
                         (.5, "alto"), (.749999, "alto"), (.75, "muy_alto"), (1, "muy_alto")):
            with self.subTest(p=p):
                self.assertEqual(risk_level(p, CORTES), nivel)
        for p in (-.1, 1.1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                risk_level(p, CORTES)
        self.assertEqual(LABELS["muy_alto"], "Muy alto")

    def test_cambio_de_alerta(self):
        self.assertEqual(alert_change(None, "alto"), "nueva")
        self.assertEqual(alert_change("alto", "alto"), "se_mantiene")
        self.assertEqual(alert_change("alto", "muy_alto"), "sube_nivel")
        self.assertEqual(alert_change("muy_alto", "alto"), "baja_nivel")

    def test_metricas_reales_de_2024_no_cumplen_y_2025_no_decide(self):
        for tarea in ("clasificacion", "regresion"):
            resultado = evaluate_model_validation(tarea, self.metricas, CRITERIOS)
            self.assertEqual(resultado["estado_validacion"], "experimental")
            self.assertEqual(set(resultado["bloques"]), {"temporada_2024"})
            sin_2025 = deepcopy(self.metricas)
            del sin_2025["bloques"]["calendario_2025"]
            self.assertEqual(resultado, evaluate_model_validation(tarea, sin_2025, CRITERIOS))

    def test_aceptacion_en_bordes_con_metricas_reales_y_limites_iguales(self):
        criterios = deepcopy(CRITERIOS)
        m = self.metricas["bloques"]["temporada_2024"]["clasificacion"]["alerta_directa"]
        criterios.update(recall_minimo=m["recall"], precision_minima=m["precision"], f1_minimo=m["f1"])
        self.assertEqual(evaluate_model_validation("clasificacion", self.metricas, criterios)["estado_validacion"], "validado")
        criterios["recall_minimo"] += .000001
        self.assertEqual(evaluate_model_validation("clasificacion", self.metricas, criterios)["estado_validacion"], "experimental")

    def test_metricas_ausentes_o_distintas_rechazan_protocolo(self):
        _compare_metrics({"a": {"b": None}}, {"a": {"b": None}})
        for actual, esperado in (({"a": 0}, {"a": None}), ({"a": 1}, {"a": 2})):
            with self.assertRaises(ValueError):
                _compare_metrics(actual, esperado)

    def test_configuracion_rechaza_valores_invalidos(self):
        """Las opciones propias del tipo (variantes de la v0) las valida su predictor al publicar."""
        original = asdict(self.cfg)
        paquete = original["paquete"]
        cambios = ({"paquete": {**paquete, "horizontes": []}}, {"paquete": {**paquete, "horizontes": [5]}},
                   {"paquete": {**paquete, "horizontes": [2, 2]}}, {"paquete": {**paquete, "tipo": "inventado"}},
                   {"paquete": {**paquete, "opciones": ["variantes"]}},
                   {"servir_no_validadas": "true"})
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "config.yaml"
            for cambio in cambios:
                ruta.write_text(yaml.safe_dump({"serving": {**original, **cambio}}), encoding="utf-8")
                with self.subTest(cambio=cambio), self.assertRaises(ValueError):
                    service_settings(ruta)
            ruta.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                service_settings(ruta)


class TestParametrosYAlmacenamiento(unittest.TestCase):
    def test_parametros_desde_la_bd(self):
        with tempfile.TemporaryDirectory() as carpeta:
            motor = motor_temporal(Path(carpeta))
            try:
                with transaction(motor) as s:
                    self.assertEqual(parametros.risk_cutoffs(s), CORTES)
                    self.assertEqual(parametros.acceptance_criteria(s), CRITERIOS)
                    self.assertEqual((parametros.default_horizon(s), parametros.interval_level(s)), (4, 0.80))
                    for clave, valor, funcion in (("nivel_intervalo_casos", {"nivel": 1.2}, parametros.interval_level),
                                                  ("horizonte_por_defecto", {"horizonte": 7}, parametros.default_horizon)):
                        anterior = s.get(SystemParameter, clave).valor
                        s.get(SystemParameter, clave).valor = valor
                        s.flush()
                        with self.subTest(clave=clave), self.assertRaises(ValueError):
                            funcion(s)
                        s.get(SystemParameter, clave).valor = anterior
                        s.flush()
                    self.assertEqual(parametros.experimental_selection(s), {})
                    parametros.set_experimental_selection(s, {2: {"clasificacion": "a", "regresion": "b"}})
                    parametros.set_experimental_selection(s, {3: {"clasificacion": "c", "regresion": "d"}})
                    self.assertEqual(parametros.experimental_selection(s),
                                     {2: {"clasificacion": "a", "regresion": "b"}, 3: {"clasificacion": "c", "regresion": "d"}})
                    s.delete(s.get(SystemParameter, "seleccion_experimental"))
                    s.flush()
                    with self.assertRaises(parametros.MissingParameter):
                        parametros.set_experimental_selection(s, {2: {"clasificacion": "a", "regresion": "b"}})
                    s.get(SystemParameter, "cortes_riesgo").valor = {"medio": .5, "alto": .25, "muy_alto": .75}
                    s.flush()
                    with self.assertRaises(ValueError):
                        parametros.risk_cutoffs(s)
                    s.delete(s.get(SystemParameter, "regla_brote"))
                    s.flush()
                    with self.assertRaises(parametros.MissingParameter):
                        parametros.read(s, "regla_brote")
            finally:
                motor.dispose()

    def test_almacenamiento_local(self):
        with tempfile.TemporaryDirectory() as carpeta:
            almacen = LocalStorage(Path(carpeta))
            self.assertFalse(almacen.exists("modelos/a.json"))
            almacen.save("modelos/a.json", b"{}")
            self.assertTrue(almacen.exists("modelos/a.json"))
            self.assertEqual(almacen.read("modelos/a.json"), b"{}")
            self.assertTrue((Path(carpeta) / "modelos" / "a.json").is_file())
            with self.assertRaises(FileNotFoundError):
                almacen.read("reportes/b.json")
            for ruta in ("otro/a.json", "modelos/../x", "a.json", "modelos\\a.json", "modelos//a"):
                with self.subTest(ruta=ruta), self.assertRaises(ValueError):
                    validate_path(ruta)


if __name__ == "__main__":
    unittest.main()
