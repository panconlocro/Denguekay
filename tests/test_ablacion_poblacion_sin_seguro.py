"""La comparación condicional conserva cuatro variantes y folds pareados."""

import unittest

import numpy as np

from src.modeling.ablacion_poblacion_sin_seguro import (
    deltas_por_temporada, validar_matriz_condicional,
    variantes_condicionales,
)
from tests.test_modeling_train import panel_sintetico


class AblacionCondicionalTests(unittest.TestCase):
    def test_variantes_aditivas_sin_objetivo(self):
        for h in (2, 4):
            v = variantes_condicionales(h)
            self.assertEqual({n: len(cols) for n, cols in v.items()},
                             {"base_6": 6, "poblacion_2017": 7,
                              "sin_seguro_2017": 7,
                              "poblacion_y_sin_seguro_2017": 8})
            self.assertEqual(v["poblacion_y_sin_seguro_2017"][:6], v["base_6"])
            self.assertFalse({"brote", "casos_Dengue", "ubigeo"} &
                             set().union(*map(set, v.values())))

    def test_matriz_completa_y_fraccion_en_rango(self):
        datos = panel_sintetico(2)
        datos = datos.loc[datos.groupby("ubigeo").cumcount().ge(5)].copy()
        datos["log_poblacion_censo_2017"] = 10.0
        datos["fraccion_sin_seguro_2017"] = 0.2
        validar_matriz_condicional(datos, 2)
        datos.loc[datos.index[0], "fraccion_sin_seguro_2017"] = np.nan
        with self.assertRaisesRegex(ValueError, "nulos"):
            validar_matriz_condicional(datos, 2)
        datos.loc[datos.index[0], "fraccion_sin_seguro_2017"] = 1.2
        with self.assertRaisesRegex(ValueError, "fuera"):
            validar_matriz_condicional(datos, 2)

    def test_deltas_pareados_no_usan_otro_tipo_de_bloque(self):
        def fold(bloque, tipo, f1):
            return {"bloque": bloque, "tipo": tipo,
                    "regresion": {"alerta_derivada": {"f1": f1}},
                    "clasificacion": {"alerta_directa": {"f1": f1}}}
        valores = {"base_6": .50, "poblacion_2017": .55,
                   "sin_seguro_2017": .56, "poblacion_y_sin_seguro_2017": .54}
        resultados = {n: {"folds_validacion": [fold("temporada_2021", "validacion", f1)],
                          "folds_prueba": [fold("temporada_2024", "prueba_principal", 1-f1)]}
                      for n, f1 in valores.items()}
        val = deltas_por_temporada(resultados, "clasificacion", tipo="validacion")
        self.assertAlmostEqual(val["ambos_menos_poblacion"]["temporada_2021"], -.01)
        self.assertAlmostEqual(val["ambos_menos_sin_seguro"]["temporada_2021"], -.02)
        prueba = deltas_por_temporada(resultados, "clasificacion", tipo="prueba_principal")
        self.assertAlmostEqual(prueba["ambos_menos_poblacion"]["temporada_2024"], .01)
        resultados["sin_seguro_2017"]["folds_validacion"] = []
        with self.assertRaisesRegex(ValueError, "mismos bloques"):
            deltas_por_temporada(resultados, "clasificacion", tipo="validacion")


if __name__ == "__main__":
    unittest.main()
