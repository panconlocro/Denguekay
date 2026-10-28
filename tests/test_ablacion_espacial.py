"""Las ablaciones espaciales conservan filas, objetivos y selección temporal."""

import unittest

import numpy as np
import pandas as pd

from src.modeling.ablacion_espacial import (
    elegir_variante_f1, resumir_silenciosos, validar_matriz_espacial,
    variantes_espaciales,
)
from src.modeling.train import preparar_gold
from tests.test_modeling_train import panel_sintetico


class AblacionEspacialTests(unittest.TestCase):
    def test_variantes_son_bloques_aditivos_sin_objetivos(self):
        for h in (2, 4):
            with self.subTest(h=h):
                v = variantes_espaciales(h)
                self.assertEqual({k: len(cols) for k, cols in v.items()},
                                 {"base_6": 6, "mas_vecinos": 8,
                                  "mas_jerarquia": 10, "mas_ambos": 12})
                self.assertEqual(v["mas_ambos"][:6], v["base_6"])
                for columnas in v.values():
                    self.assertFalse({"casos_Dengue", "brote", "umbral_brote_casos",
                                      "ubigeo", "anio", "semana"} & set(columnas))

    def test_mismas_filas_completas_para_todas_las_variantes(self):
        panel = panel_sintetico(2)
        v = variantes_espaciales(2)
        for columna in set().union(*map(set, v.values())) - set(panel):
            panel[columna] = 1.0
        datos, _ = preparar_gold(panel, 2)
        validar_matriz_espacial(datos, v)
        self.assertEqual(len(datos), 30)
        datos.loc[datos.index[-1], v["mas_vecinos"][-1]] = np.nan
        with self.assertRaisesRegex(ValueError, "nulos"):
            validar_matriz_espacial(datos, v)

    def test_seleccion_ignora_resultados_de_prueba(self):
        variantes = {"base": ["a"], "nueva": ["a", "b"]}
        def fold(valor):
            return {"tipo": "validacion",
                    "regresion": {"alerta_derivada": {"f1": valor}},
                    "clasificacion": {"alerta_directa": {"f1": valor}}}
        resumen = {
            "base": {"folds_validacion": [fold(0.50), fold(0.50), fold(0.50)],
                     "folds_prueba": [{"f1": 1.0}]},
            "nueva": {"folds_validacion": [fold(0.60), fold(0.60), fold(0.60)],
                      "folds_prueba": [{"f1": 0.0}]},
        }
        self.assertEqual(elegir_variante_f1(resumen, "clasificacion", variantes), "nueva")
        self.assertEqual(elegir_variante_f1(resumen, "regresion", variantes), "nueva")

    def test_empate_prefiere_menos_columnas_y_rechaza_prueba_en_validacion(self):
        v = {"base": ["a"], "nueva": ["a", "b"]}
        fold = {"tipo": "validacion", "regresion": {"alerta_derivada": {"f1": 0.5}},
                "clasificacion": {"alerta_directa": {"f1": 0.5}}}
        r = {nombre: {"folds_validacion": [fold]} for nombre in v}
        self.assertEqual(elegir_variante_f1(r, "clasificacion", v), "base")
        r["nueva"]["folds_validacion"] = [{**fold, "tipo": "prueba_principal"}]
        with self.assertRaisesRegex(ValueError, "solo admite folds de validación"):
            elegir_variante_f1(r, "clasificacion", v)

    def test_auditoria_silenciosos_cuenta_alertas_sin_confundir_ceros(self):
        pred = pd.DataFrame({
            "ubigeo": ["200204", "200204", "200101"],
            "casos_predichos": [3.0, 1.0, 5.0],
            "umbral_brote_casos": [0.0, 0.0, 0.0],
            "probabilidad_brote": [0.3, 0.1, 0.8],
            "brote": [0, 0, 1],
        })
        resumen = resumir_silenciosos(pred, ["200204"], 0.2)
        self.assertEqual(resumen, {"filas": 2, "positivos_observados": 0,
                                  "alertas_regresion": 1,
                                  "alertas_clasificacion": 1})


if __name__ == "__main__":
    unittest.main()
