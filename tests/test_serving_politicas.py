"""Aceptación por 2024, faltantes y cortes de riesgo acordados con Rosa."""

from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest

import yaml

from serving_soporte import protocolo_muestra
from src.db.modelos import VersionModelo
from src.serving.configuracion import configuracion_servicio
from src.serving.protocolo import _comparar_metricas, metricas_de_variante
from src.serving.riesgo import disponibilidad_modelo, genera_alerta, nivel_riesgo
from src.validation.validacion_modelo import evaluar_validacion_modelo


class TestPoliticasServicio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = configuracion_servicio()
        cls.metricas = metricas_de_variante(protocolo_muestra(), 2, "base_6_poblacion_2017")

    def test_bordes_de_riesgo_y_alertas_visibles_desde_05(self):
        for p, nivel in ((None, "Sin datos"), (0, "Bajo"), (.249999, "Bajo"), (.25, "Medio"),
                         (.499999, "Medio"), (.5, "Alto"), (.749999, "Alto"), (.75, "Muy alto"), (1, "Muy alto")):
            with self.subTest(p=p):
                self.assertEqual(nivel_riesgo(p, self.cfg.riesgo), nivel)
                self.assertEqual(genera_alerta(nivel), nivel in ("Alto", "Muy alto"))
        self.assertFalse(genera_alerta("Alto", "Muy alto"))
        with self.assertRaises(ValueError):
            genera_alerta("Bajo", "Medio")
        for p in (-.1, 1.1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                nivel_riesgo(p, self.cfg.riesgo)

    def test_metricas_reales_de_2024_no_cumplen_y_2025_no_decide(self):
        for tipo in ("clasificacion", "regresion"):
            resultado = evaluar_validacion_modelo(tipo, self.metricas, self.cfg.criterios_validacion)
            self.assertEqual(resultado["estado_validacion"], "experimental")
            self.assertEqual(set(resultado["bloques"]), {"temporada_2024"})
            sin_2025 = deepcopy(self.metricas)
            del sin_2025["bloques"]["calendario_2025"]
            self.assertEqual(resultado, evaluar_validacion_modelo(tipo, sin_2025, self.cfg.criterios_validacion))

    def test_aceptacion_en_bordes_con_metricas_reales_y_limites_iguales(self):
        criterios = deepcopy(self.cfg.criterios_validacion)
        m = self.metricas["bloques"]["temporada_2024"]["clasificacion"]["alerta_directa"]
        criterios.update(recall_minimo=m["recall"], precision_minima=m["precision"], f1_minimo=m["f1"])
        self.assertEqual(evaluar_validacion_modelo("clasificacion", self.metricas, criterios)["estado_validacion"], "validado")
        criterios["recall_minimo"] += .000001
        self.assertEqual(evaluar_validacion_modelo("clasificacion", self.metricas, criterios)["estado_validacion"], "experimental")

    def test_faltante_no_es_cero_y_persistencia_es_referencia(self):
        metricas = deepcopy(self.metricas)
        metricas["bloques"]["temporada_2024"]["clasificacion"]["alerta_directa"]["recall"] = None
        estado = evaluar_validacion_modelo("clasificacion", metricas, self.cfg.criterios_validacion)
        self.assertFalse(estado["disponible"])
        self.assertIsNone(estado["bloques"]["temporada_2024"]["criterios"]["recall"]["valor"])
        self.assertIn("no disponible", estado["motivo"])
        for tipo in ("clasificacion", "regresion", "desconocido"):
            self.assertEqual(evaluar_validacion_modelo(tipo, {}, {})["estado_validacion"], "experimental")
        self.assertEqual(evaluar_validacion_modelo("persistencia", {}, {})["estado_validacion"], "referencia")
        estado = evaluar_validacion_modelo("clasificacion", {}, self.cfg.criterios_validacion)
        self.assertFalse(estado["disponible"])

    def test_disponibilidad_no_oculta_estado_experimental(self):
        v = VersionModelo(tipo="clasificacion", metricas_evaluacion=self.metricas,
                          criterios_validacion=self.cfg.criterios_validacion)
        self.assertEqual(v.estado_validacion, "experimental")
        self.assertFalse(disponibilidad_modelo(v, False)["disponible"])
        self.assertTrue(disponibilidad_modelo(v, True)["disponible"])
        self.assertFalse(disponibilidad_modelo(None, True)["disponible"])

    def test_metricas_ausentes_o_distintas_rechazan_protocolo(self):
        _comparar_metricas({"a": {"b": None}}, {"a": {"b": None}})
        for actual, esperado in (({"a": 0}, {"a": None}), ({"a": 1}, {"a": 2})):
            with self.assertRaises(ValueError):
                _comparar_metricas(actual, esperado)

    def test_configuracion_rechaza_umbral_variante_o_politica_invalidos(self):
        original = asdict(self.cfg)
        cambios = ({"horizontes": []}, {"variantes": {"clasificacion": "inventada", "regresion": "base_6"}},
                   {"riesgo": {"medio": .5, "alto": .25, "muy_alto": .75}},
                   {"alerta_nivel_minimo": "Medio"}, {"servir_no_validadas": "true"},
                   {"criterios_validacion": {**original["criterios_validacion"], "bloques": []}},
                   {"criterios_validacion": {**original["criterios_validacion"], "precision_minima": None}})
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "config.yaml"
            for cambio in cambios:
                ruta.write_text(yaml.safe_dump({"serving": {**original, **cambio}}), encoding="utf-8")
                with self.subTest(cambio=cambio), self.assertRaises(ValueError):
                    configuracion_servicio(ruta)
            ruta.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                configuracion_servicio(ruta)


if __name__ == "__main__":
    unittest.main()
