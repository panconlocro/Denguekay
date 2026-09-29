"""Tests de src/eda/calidad.py con datos sintéticos (no dependen de data/)."""

import unittest

import numpy as np
import pandas as pd

from src.eda.calidad import (
    columnas_identicas, desvio_de_linea_recta, distritos_con_serie_identica, reglas_consistencia,
    semana_epi_mmwr, variacion_intra_anual, z_robusto,
)


class SemanaEpiMmwrTests(unittest.TestCase):
    def test_casos_conocidos(self):
        fechas = pd.Series(pd.to_datetime([
            "2017-01-01",  # SE 1 de 2017
            "2020-12-27",  # SE 53 de 2020
            "2021-01-03",  # SE 1 de 2021
            "2024-12-29",  # SE 1 de 2025 (miércoles 1 de enero)
            "2025-12-21",  # SE 52 de 2025
            "2025-12-28",  # SE 53 de 2025 (miércoles 31 de diciembre)
            "2026-01-04",  # SE 1 de 2026
        ]))
        r = semana_epi_mmwr(fechas)
        esperado = [(2017, 1), (2020, 53), (2021, 1), (2025, 1), (2025, 52), (2025, 53), (2026, 1)]
        self.assertEqual(list(zip(r["anio_epi"], r["semana_epi"])), esperado)

    def test_rechaza_fechas_que_no_son_domingo(self):
        with self.assertRaises(ValueError):
            semana_epi_mmwr(pd.Series(pd.to_datetime(["2017-01-02"])))


class ChequeosTests(unittest.TestCase):
    def test_columnas_identicas(self):
        df = pd.DataFrame({"a": [1, 2], "b": [1, 2], "c": [1, 3]})
        self.assertEqual(columnas_identicas(df), [("a", "b")])

    def test_distritos_con_serie_identica(self):
        fechas = pd.to_datetime(["2017-01-01", "2017-01-08"])
        df = pd.DataFrame({
            "ubigeo": ["200101", "200101", "200102", "200102", "200103", "200103"],
            "semana_inicio": list(fechas) * 3,
            "x": [1.0, 2.0, 1.0, 2.0, 1.0, 3.0],
        })
        self.assertEqual(distritos_con_serie_identica(df, "x"), [["200101", "200102"]])

    def test_reglas_consistencia_cuenta_violaciones(self):
        df = pd.DataFrame({
            "temp_min": [10, 20], "temp_media": [15, 15], "temp_max": [20, 25],
            "hum_rel_media": [50, 101], "fraccion_x": [0.5, 1.2],
        })
        r = reglas_consistencia(df)
        self.assertEqual(r["temp_min > temp_media"], 1)
        self.assertEqual(r["hum_rel_media fuera de [0, 100]"], 1)
        self.assertEqual(r["alguna fraccion_* fuera de [0, 1]"], 1)
        self.assertNotIn("precip_total_mm < 0", r.index)  # columna ausente: regla omitida

    def test_variacion_intra_anual(self):
        df = pd.DataFrame({"ubigeo": ["200101"] * 3, "anio": [2017, 2017, 2018], "x": [1, 2, 3]})
        self.assertEqual(variacion_intra_anual(df, ["x"])["x"], 1)

    def test_desvio_de_linea_recta(self):
        anios = np.arange(2017, 2026)
        lineal = pd.DataFrame({"ubigeo": "200101", "anio": anios, "x": np.linspace(0, 0.8, 9)})
        self.assertAlmostEqual(desvio_de_linea_recta(lineal, ["x"]).loc["200101", "x"], 0.0)
        curvo = lineal.assign(x=lineal["x"] ** 2)
        self.assertGreater(desvio_de_linea_recta(curvo, ["x"]).loc["200101", "x"], 0.1)

    def test_z_robusto_por_grupo(self):
        df = pd.DataFrame({"g": ["a"] * 5 + ["b"] * 3, "x": [1, 2, 3, 4, 100, 5, 5, 5]})
        z = z_robusto(df, "x", "g")
        self.assertGreater(z.iloc[4], 10)
        self.assertTrue(z.iloc[5:].isna().all())  # MAD = 0 -> NaN


if __name__ == "__main__":
    unittest.main()
