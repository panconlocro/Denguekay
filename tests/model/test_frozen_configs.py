"""Configuración congelada para 2026 y diccionario de variables (fase 5 del encargo de FE)."""

import json
import unittest

import pandas as pd

from denguekay.model import frozen_configs as cf
from denguekay.model import variable_dictionary as dv
from denguekay.model import horizon_strategies as eh
from src.modeling import hiperparametros as hp
from denguekay.model import probabilistic_output as sp
from denguekay.config.paths import FE_HYPERPARAMETERS_EXPERIMENTS, GOLD_MANIFEST, SILVER_EPI_HISTORICAL, SILVER_INTEGRATED

GUARDADAS = FE_HYPERPARAMETERS_EXPERIMENTS / "fase4" / "predicciones_s4s3_dentro_muestra.csv.gz"
GUARDADAS_V2 = FE_HYPERPARAMETERS_EXPERIMENTS / "complemento_clima" / "predicciones_F_A3.csv.gz"
HAY_DATOS = SILVER_INTEGRATED.exists() and GOLD_MANIFEST.exists() and SILVER_EPI_HISTORICAL.exists()


class TestConfiguracion(unittest.TestCase):
    def test_constante_coherente(self):
        v1, c = cf.CONFIGURACION_2026_V1, cf.CONFIGURACION_2026
        self.assertEqual(len(v1["columnas"]), 9)
        self.assertEqual(c["columnas"], [*v1["columnas"], *cf.COLUMNAS_A3])
        self.assertEqual({k: v for k, v in c.items() if k not in ("columnas", "matriz", "version", "decisiones",
                                                                  "fecha_congelamiento", "filas_excluidas")},
                         {k: v for k, v in v1.items() if k not in ("columnas", "matriz", "decisiones",
                                                                   "fecha_congelamiento")})
        self.assertEqual(c["columnas"][:6], eh.GENERICAS)
        self.assertEqual(cf.HISTORIAL["V2"]["estado"], "vigente")
        # Huellas con la definición original (configuración + código): históricas desde la reestructuración (D1).
        self.assertEqual(cf.HISTORICAL_FINGERPRINTS["V1"]["sha256"],
                         "88ed2a43b0171a0878b99122b70109be61b27d5d4d29a2b93eae55066fd8f945")
        self.assertEqual(cf.HISTORICAL_FINGERPRINTS["V2"]["sha256"],
                         "c36d7a80d1896a203874bf271bd78f1078850e1faa381e2b17e9ba04b07d5569")
        self.assertEqual({h["commit"] for h in cf.HISTORICAL_FINGERPRINTS.values()}, {"d6bd0be", "424a148"})
        self.assertIn(c["formulacion"], sp.FORMULACIONES)
        self.assertIn(c["dispersion"], sp.DISPERSIONES)
        self.assertEqual(c["hiperparametros"], hp.BASE)
        self.assertEqual(c["semilla_despliegue"], 17)
        for valores in cf.REFERENCE_FINGERPRINTS.values():
            self.assertEqual(set(valores), {"V1", "V2"})
            self.assertTrue(all(len(v) == 64 for v in valores.values()))

    def test_huella_de_comportamiento(self):
        p = pd.DataFrame({"ubigeo": ["200101", "200102"], "semana_inicio": ["2024-01-07"] * 2, "horizonte": [2, 2],
                          "bloque": ["b"] * 2, "casos_predichos": [1.5, 0.0], "probabilidad_brote": [0.25, 0.0]})
        h = cf.fingerprint(p)
        self.assertEqual(h, cf.fingerprint(p.iloc[::-1]))  # orden canónico
        self.assertNotEqual(h, cf.fingerprint(p, cf.CONFIGURACION_2026_V1))
        self.assertNotEqual(h, cf.fingerprint(p.assign(casos_predichos=[1.5, 1e-300])))  # bit a bit
        self.assertEqual(cf.setup_key({"device": "cpu", "n_jobs": 2}), "device=cpu,n_jobs=2")
        self.assertEqual(cf.setup_key({"device": "cuda", "n_jobs": 12}), "device=cuda")

    def test_minimos_de_evaluacion(self):
        self.assertFalse(cf.evaluable(3, "brote"))
        self.assertTrue(cf.evaluable(30, "brote"))
        self.assertFalse(cf.evaluable(19, "inicios"))
        self.assertTrue(cf.evaluable(20, "inicios"))
        with self.assertRaises(KeyError):
            cf.evaluable(10, "otro")


class TestDiccionario(unittest.TestCase):
    def test_cubre_exactamente_las_columnas_finales(self):
        self.assertEqual(dv.diccionario(cf.CONFIGURACION_2026_V1["columnas"]).variable.tolist(),
                         cf.CONFIGURACION_2026_V1["columnas"])
        tabla = dv.diccionario(cf.CONFIGURACION_2026["columnas"])
        self.assertEqual(tabla.variable.tolist(), cf.CONFIGURACION_2026["columnas"])
        campos = ["fuente", "definicion", "ventana", "transformacion", "tipo", "nulos", "por_que", "evidencia",
                  "test_no_fuga"]
        self.assertFalse(tabla[campos].isna().any().any())
        self.assertEqual(tabla.columna_gold_h2.iloc[0], "casos_lag_2")
        with self.assertRaises(ValueError):
            dv.diccionario(["inventada"])

    def test_estadisticas_y_markdown(self):
        o = pd.DataFrame({"temporada": [2017, 2017, 2018], "hist_lag_a": [0.0, 4.0, None]})
        e = dv.estadisticas(o, ["hist_lag_a"]).set_index("temporada")
        self.assertEqual((e.loc[2017, "maximo"], e.loc[2017, "nulos"], e.loc[2018, "nulos"]), (4.0, 0, 1))
        texto = dv.a_markdown(dv.diccionario(["hist_lag_a"]), e.reset_index(), cf.CONFIGURACION_2026)
        self.assertIn("## `hist_lag_a`", texto)
        self.assertIn("margen de persistencia", texto)


@unittest.skipUnless(HAY_DATOS and GUARDADAS.exists() and GUARDADAS_V2.exists(),
                     "requiere datos y las predicciones guardadas de la fase 4 y del complemento")
class TestReproduccion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.eda.carga import cargar_integrado
        from src.modeling import fe_hiperparametros as fh

        cls.panel = cargar_integrado(SILVER_INTEGRATED)
        cls.regla = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
        cls.ins = fh.insumos(cls.panel, cls.regla)

    def _comprobar(self, nombre, configuracion, ruta):
        from denguekay.model.device import configuracion_xgboost

        o = cf.origenes(self.panel, self.ins, self.regla, configuracion=configuracion)
        pred = cf.predecir(self.ins["matrices"], o, configuracion=configuracion)
        guardadas = pd.read_csv(ruta, dtype={"ubigeo": "string"})
        r = cf.coincide_con_guardadas(pred, guardadas[guardadas.semilla.eq(cf.SEMILLA_DESPLIEGUE)])
        self.assertTrue(r["coincide"], r)
        # Huella de comportamiento: misma configuración y predicciones idénticas bit a bit.
        referencia = cf.REFERENCE_FINGERPRINTS.get(cf.setup_key(configuracion_xgboost()))
        if referencia is not None:
            self.assertEqual(cf.fingerprint(pred, configuracion), referencia[nombre])

    def test_v1_reproduce_la_fase_4_con_la_semilla_de_despliegue(self):
        self._comprobar("V1", cf.CONFIGURACION_2026_V1, GUARDADAS)

    def test_v2_reproduce_el_complemento_con_la_semilla_de_despliegue(self):
        self._comprobar("V2", cf.CONFIGURACION_2026, GUARDADAS_V2)


if __name__ == "__main__":
    unittest.main()
