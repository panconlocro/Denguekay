"""Configuración congelada para 2026 y diccionario de variables (fase 5 del encargo de FE)."""

import json
import unittest

import pandas as pd

from src.modeling import configuracion_final as cf
from src.modeling import diccionario_variables as dv
from src.modeling import estrategias_horizonte as eh
from src.modeling import hiperparametros as hp
from src.modeling import salida_probabilistica as sp
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
        # La huella de la V1 no cambia al agregar la V2.
        self.assertEqual(cf.huella(v1), "88ed2a43b0171a0878b99122b70109be61b27d5d4d29a2b93eae55066fd8f945")
        self.assertIn(c["formulacion"], sp.FORMULACIONES)
        self.assertIn(c["dispersion"], sp.DISPERSIONES)
        self.assertEqual(c["hiperparametros"], hp.BASE)
        self.assertEqual(c["semilla_despliegue"], 17)
        self.assertEqual(len(cf.huella()), 64)

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

    def _comprobar(self, configuracion, ruta):
        o = cf.origenes(self.panel, self.ins, self.regla, configuracion=configuracion)
        pred = cf.predecir(self.ins["matrices"], o, configuracion=configuracion)
        guardadas = pd.read_csv(ruta, dtype={"ubigeo": "string"})
        r = cf.coincide_con_guardadas(pred, guardadas[guardadas.semilla.eq(cf.SEMILLA_DESPLIEGUE)])
        self.assertTrue(r["coincide"], r)

    def test_v1_reproduce_la_fase_4_con_la_semilla_de_despliegue(self):
        self._comprobar(cf.CONFIGURACION_2026_V1, GUARDADAS)

    def test_v2_reproduce_el_complemento_con_la_semilla_de_despliegue(self):
        self._comprobar(cf.CONFIGURACION_2026, GUARDADAS_V2)


if __name__ == "__main__":
    unittest.main()
