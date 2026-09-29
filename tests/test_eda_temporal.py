"""Tests de src/eda/temporal.py con datos sintéticos (no dependen de data/)."""

import unittest

import numpy as np
import pandas as pd

from src.eda.temporal import (
    acf_simple, asignar_temporada, metricas_binarias, perfil_normalizado,
    prediccion_estacional, prediccion_persistencia, semana_valle,
)


class AcfTests(unittest.TestCase):
    def test_coincide_con_statsmodels(self):
        from statsmodels.tsa.stattools import acf
        x = np.random.default_rng(0).normal(size=200).cumsum()
        np.testing.assert_allclose(acf_simple(x, 8), acf(x, nlags=8), atol=1e-10)

    def test_serie_constante_devuelve_nan(self):
        self.assertTrue(np.isnan(acf_simple(np.ones(10), 3)).all())


class TemporadaTests(unittest.TestCase):
    def test_asignar_temporada(self):
        t = asignar_temporada(pd.Series([2022, 2022, 2023]), pd.Series([35, 36, 10]), semana_inicio=36)
        self.assertEqual(t.tolist(), [2022, 2023, 2023])

    def test_semana_valle(self):
        df = pd.DataFrame({"anio": 2017, "semana": range(1, 53), "casos_Dengue": [10] * 52})
        df.loc[df["semana"] == 40, "casos_Dengue"] = 1
        self.assertEqual(semana_valle(perfil_normalizado(df)), 40)


class LineasBaseTests(unittest.TestCase):
    def test_persistencia_no_cruza_distritos(self):
        df = pd.DataFrame({"ubigeo": ["a"] * 3 + ["b"] * 3, "y": [1, 2, 3, 10, 20, 30]})
        self.assertTrue(np.isnan(prediccion_persistencia(df, "y", 1).iloc[3]))
        self.assertEqual(prediccion_persistencia(df, "y", 2).iloc[5], 10)

    def test_estacional_alinea_por_semana_y_trata_la_53(self):
        df = pd.DataFrame({"ubigeo": "a", "anio": [2020, 2020, 2020, 2021, 2021],
                           "semana": [1, 52, 53, 1, 52], "y": [5, 7, 9, 11, 13]})
        pred = prediccion_estacional(df, "y")
        self.assertTrue(pred.iloc[:3].isna().all())       # 2019 no existe
        self.assertEqual(pred.iloc[3:].tolist(), [5, 7])  # misma semana de 2020, pese a la semana 53
        df2 = pd.DataFrame({"ubigeo": "a", "anio": [2019, 2020], "semana": [52, 53], "y": [4, 0]})
        self.assertEqual(prediccion_estacional(df2, "y").iloc[1], 4)  # la 53 se compara con la 52

    def test_metricas_binarias(self):
        r = metricas_binarias(pd.Series([1, 1, 0, 0]), pd.Series([1, 0, 1, 0]))
        self.assertEqual((r["precision"], r["recall"], r["f1"]), (0.5, 0.5, 0.5))

    def test_metricas_binarias_sin_positivos_no_definidas(self):
        r = metricas_binarias(pd.Series([0, 0]), pd.Series([0, 0]))
        self.assertTrue(np.isnan(r["recall"]) and np.isnan(r["f1"]))
        r = metricas_binarias(pd.Series([1, 0]), pd.Series([0, 0]))
        self.assertEqual(r["f1"], 0.0)


if __name__ == "__main__":
    unittest.main()
