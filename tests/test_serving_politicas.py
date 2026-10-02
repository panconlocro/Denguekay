"""Riesgo, aceptación, configuración, parámetros de la BD y almacenamiento local."""

from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest

import yaml

from backend_soporte import motor_temporal
from serving_soporte import protocolo_muestra
from src.db.modelos import ParametroSistema
from src.db.sesion import transaccion
from src.serving import parametros
from src.serving.almacenamiento import AlmacenamientoLocal, validar_ruta
from src.serving.configuracion import configuracion_servicio
from src.serving.protocolo import _comparar_metricas, metricas_de_variante
from src.serving.riesgo import ETIQUETAS, cambio_alerta, nivel_riesgo
from src.validation.validacion_modelo import evaluar_validacion_modelo

CORTES = {"medio": 0.25, "alto": 0.50, "muy_alto": 0.75}
CRITERIOS = {"bloques": ["temporada_2024"], "recall_minimo": 0.8, "precision_minima": 0.6,
             "f1_minimo": 0.7, "proporcion_error_persistencia": 0.85}


class TestPoliticasServicio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = configuracion_servicio()
        cls.metricas = metricas_de_variante(protocolo_muestra(), 2, "base_6_poblacion_2017")

    def test_bordes_de_riesgo(self):
        for p, nivel in ((None, None), (0, "bajo"), (.249999, "bajo"), (.25, "medio"), (.499999, "medio"),
                         (.5, "alto"), (.749999, "alto"), (.75, "muy_alto"), (1, "muy_alto")):
            with self.subTest(p=p):
                self.assertEqual(nivel_riesgo(p, CORTES), nivel)
        for p in (-.1, 1.1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                nivel_riesgo(p, CORTES)
        self.assertEqual(ETIQUETAS["muy_alto"], "Muy alto")

    def test_cambio_de_alerta(self):
        self.assertEqual(cambio_alerta(None, "alto"), "nueva")
        self.assertEqual(cambio_alerta("alto", "alto"), "se_mantiene")
        self.assertEqual(cambio_alerta("alto", "muy_alto"), "sube_nivel")
        self.assertEqual(cambio_alerta("muy_alto", "alto"), "baja_nivel")

    def test_metricas_reales_de_2024_no_cumplen_y_2025_no_decide(self):
        for tarea in ("clasificacion", "regresion"):
            resultado = evaluar_validacion_modelo(tarea, self.metricas, CRITERIOS)
            self.assertEqual(resultado["estado_validacion"], "experimental")
            self.assertEqual(set(resultado["bloques"]), {"temporada_2024"})
            sin_2025 = deepcopy(self.metricas)
            del sin_2025["bloques"]["calendario_2025"]
            self.assertEqual(resultado, evaluar_validacion_modelo(tarea, sin_2025, CRITERIOS))

    def test_aceptacion_en_bordes_con_metricas_reales_y_limites_iguales(self):
        criterios = deepcopy(CRITERIOS)
        m = self.metricas["bloques"]["temporada_2024"]["clasificacion"]["alerta_directa"]
        criterios.update(recall_minimo=m["recall"], precision_minima=m["precision"], f1_minimo=m["f1"])
        self.assertEqual(evaluar_validacion_modelo("clasificacion", self.metricas, criterios)["estado_validacion"], "validado")
        criterios["recall_minimo"] += .000001
        self.assertEqual(evaluar_validacion_modelo("clasificacion", self.metricas, criterios)["estado_validacion"], "experimental")

    def test_metricas_ausentes_o_distintas_rechazan_protocolo(self):
        _comparar_metricas({"a": {"b": None}}, {"a": {"b": None}})
        for actual, esperado in (({"a": 0}, {"a": None}), ({"a": 1}, {"a": 2})):
            with self.assertRaises(ValueError):
                _comparar_metricas(actual, esperado)

    def test_configuracion_rechaza_valores_invalidos(self):
        original = asdict(self.cfg)
        cambios = ({"horizontes": []}, {"horizontes": [3]}, {"variantes": {"clasificacion": "inventada", "regresion": "base_6"}},
                   {"servir_no_validadas": "true"}, {"seleccion_experimental": {"2": {"clasificacion": "x"}}},
                   {"seleccion_experimental": {"2": {"clasificacion": "x" * 21, "regresion": "y"}}})
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "config.yaml"
            for cambio in cambios:
                ruta.write_text(yaml.safe_dump({"serving": {**original, **cambio}}), encoding="utf-8")
                with self.subTest(cambio=cambio), self.assertRaises(ValueError):
                    configuracion_servicio(ruta)
            ruta.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                configuracion_servicio(ruta)


class TestParametrosYAlmacenamiento(unittest.TestCase):
    def test_parametros_desde_la_bd(self):
        with tempfile.TemporaryDirectory() as carpeta:
            motor = motor_temporal(Path(carpeta))
            try:
                with transaccion(motor) as s:
                    self.assertEqual(parametros.cortes_riesgo(s), CORTES)
                    self.assertEqual(parametros.criterios_aceptacion(s), CRITERIOS)
                    self.assertEqual(parametros.seleccion_experimental(s), {})
                    parametros.sembrar_seleccion_experimental(s, {2: {"clasificacion": "a", "regresion": "b"}})
                    self.assertEqual(parametros.seleccion_experimental(s)[2]["regresion"], "b")
                    s.get(ParametroSistema, "cortes_riesgo").valor = {"medio": .5, "alto": .25, "muy_alto": .75}
                    s.flush()
                    with self.assertRaises(ValueError):
                        parametros.cortes_riesgo(s)
                    s.delete(s.get(ParametroSistema, "regla_brote"))
                    s.flush()
                    with self.assertRaises(parametros.ParametroFaltante):
                        parametros.leer(s, "regla_brote")
            finally:
                motor.dispose()

    def test_almacenamiento_local(self):
        with tempfile.TemporaryDirectory() as carpeta:
            almacen = AlmacenamientoLocal(Path(carpeta))
            self.assertFalse(almacen.existe("modelos/a.json"))
            almacen.guardar("modelos/a.json", b"{}")
            self.assertTrue(almacen.existe("modelos/a.json"))
            self.assertEqual(almacen.leer("modelos/a.json"), b"{}")
            self.assertTrue((Path(carpeta) / "modelos" / "a.json").is_file())
            with self.assertRaises(FileNotFoundError):
                almacen.leer("reportes/b.json")
            for ruta in ("otro/a.json", "modelos/../x", "a.json", "modelos\\a.json", "modelos//a"):
                with self.subTest(ruta=ruta), self.assertRaises(ValueError):
                    validar_ruta(ruta)


if __name__ == "__main__":
    unittest.main()
