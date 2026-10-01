"""Pruebas de selección y disponibilidad de etiquetas por origen."""

import unittest

import pandas as pd

from src.modeling.validacion_temporal_compacta import (
    calibracion_disponible, elegir_en_validacion, validar_matriz,
    variantes_compactas,
)


class TestValidacionTemporalCompacta(unittest.TestCase):
    def test_variantes_pequenas_sin_objetivos(self):
        for h in (2, 4):
            variantes = variantes_compactas(h)
            self.assertEqual({k: len(v) for k, v in variantes.items()},
                             {"base_4": 4, "base_6": 6, "base_6_poblacion_2017": 7})
            self.assertEqual(variantes["base_6_poblacion_2017"][:-1], variantes["base_6"])
            self.assertFalse({"casos_Dengue", "brote", "ubigeo"} & set(sum(variantes.values(), [])))

    def test_calibracion_excluye_etiqueta_no_cerrada(self):
        anteriores = pd.DataFrame({
            "ubigeo": ["200101"] * 3,
            "anio": [2021, 2021, 2022], "semana": [1, 2, 1],
            "semana_inicio": pd.to_datetime(["2021-01-03", "2021-01-10", "2022-01-02"]),
            "brote": [0, 1, 1], "probabilidad_brote": [0.1, 0.8, 0.9],
        })
        disponibles, excluidas = calibracion_disponible(
            [anteriores], pd.Timestamp("2021-01-17"))
        self.assertEqual(len(disponibles), 2)
        self.assertEqual(excluidas, 1)
        self.assertTrue((disponibles.semana_inicio + pd.Timedelta(days=6)).le("2021-01-17").all())
        with self.assertRaisesRegex(ValueError, "dos clases"):
            calibracion_disponible([anteriores], pd.Timestamp("2021-01-09"))

    def test_matriz_rechaza_poblacion_no_fija(self):
        variantes = variantes_compactas(4)
        cols = set(sum(variantes.values(), []))
        datos = pd.DataFrame({c: [1.0, 1.0] for c in cols})
        datos["ubigeo"] = ["200101", "200101"]
        datos["anio"] = [2021, 2021]
        datos["semana"] = [1, 2]
        validar_matriz(datos, 4)
        datos["log_poblacion_censo_2017"] = [1.0, 2.0]
        with self.assertRaisesRegex(ValueError, "fija"):
            validar_matriz(datos, 4)

    def test_seleccion_ignora_2024(self):
        variantes = {"corta": ["a"], "larga": ["a", "b"]}
        def fold(temporada, f1):
            return {"bloque": f"temporada_{temporada}",
                    "clasificacion": {"alerta_directa": {"f1": f1}},
                    "regresion": {"alerta_derivada": {"f1": f1}}}
        resultados = {
            "corta": {"folds": [fold(2022, 0.7), fold(2023, 0.7), fold(2024, 0.0)]},
            "larga": {"folds": [fold(2022, 0.6), fold(2023, 0.6), fold(2024, 1.0)]},
        }
        self.assertEqual(elegir_en_validacion(resultados, "clasificacion", variantes), "corta")
        self.assertEqual(elegir_en_validacion(resultados, "regresion", variantes), "corta")


if __name__ == "__main__":
    unittest.main()
