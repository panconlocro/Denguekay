"""Pruebas del diagnóstico de errores de la fase 1 de arquitectura."""

import unittest

import numpy as np
import pandas as pd

from src.modeling import diagnostico_arquitectura as d


def _etiquetas(brotes: list[int], ubigeo: str = "200101") -> pd.DataFrame:
    semanas = pd.date_range("2022-01-02", periods=len(brotes), freq="7D")
    return pd.DataFrame({"ubigeo": ubigeo, "semana_inicio": semanas, "brote": brotes})


class TestDiagnosticoArquitectura(unittest.TestCase):
    def test_nivel_casos_limites(self):
        niveles = d.nivel_casos(pd.Series([0, 1, 4, 5, 19, 20, 99, 100, 500]))
        self.assertEqual(list(niveles.astype(str)),
                         ["0", "1–4", "1–4", "5–19", "5–19", "20–99", "20–99", "≥100", "≥100"])

    def test_episodios_unen_huecos_cortos(self):
        # 1 1 0 0 1 | 0 0 0 1 -> dos episodios (hueco de 2 se une, de 3 no)
        eps = d.episodios(_etiquetas([1, 1, 0, 0, 1, 0, 0, 0, 1]))
        self.assertEqual(len(eps), 2)
        self.assertEqual(list(eps.semanas_brote), [3, 1])
        self.assertTrue(np.isinf(eps.semanas_previas_sin_brote.iloc[0]))
        self.assertEqual(eps.semanas_previas_sin_brote.iloc[1], 3)

    def test_adyacencia_a_brote(self):
        et = _etiquetas([0, 0, 0, 0, 1, 0, 0, 0, 0, 0])
        filas = et.iloc[[1, 2, 6, 7, 9]][["ubigeo", "semana_inicio"]]
        self.assertEqual(list(d.adyacente_a_brote(filas, et)), [False, True, True, False, False])

    def test_antelacion_formula(self):
        # episodio inicia en la semana 5 (índice 5); alerta con objetivo en la semana 4
        brotes = [0] * 5 + [1, 1] + [0] * 5
        et = _etiquetas(brotes)
        datos = et.assign(horizonte=4, bloque="temporada_2022",
                          alerta_x=[False] * 4 + [True] + [False] * 7,
                          alerta_y=[False] * 12)
        tabla = d.antelacion_episodios(datos, et, ["alerta_x", "alerta_y"])
        self.assertEqual(tabla.alerta_x.iloc[0], 4 - (4 - 5))  # 5 semanas antes del inicio
        self.assertTrue(np.isnan(tabla.alerta_y.iloc[0]))
        resumen = d.resumen_antelacion(tabla, ["alerta_x", "alerta_y"])
        self.assertEqual(resumen.set_index("alerta").loc["alerta_x", "antelacion_2_o_mas"], 1.0)
        self.assertEqual(resumen.set_index("alerta").loc["alerta_y", "detectados"], 0.0)

    def test_fase_curva_regional(self):
        semanas = pd.date_range("2022-01-02", periods=5, freq="7D")
        datos = pd.DataFrame({"horizonte": 2, "bloque": "b", "semana_inicio": semanas,
                              "casos_Dengue": [0, 50, 100, 30, 5]})
        self.assertEqual(list(d.fase_curva(datos).astype(str)),
                         ["valle", "subida", "pico", "bajada", "valle"])

    def test_desglose_y_concentracion(self):
        datos = pd.DataFrame({
            "horizonte": 2, "bloque": ["temporada_2023", "temporada_2024"] * 2,
            "ubigeo": ["200101", "200101", "200102", "200102"],
            "casos_Dengue": [10.0, 0, 2, 0], "casos_predichos": [6.0, 1, 2, 0],
            "persistencia": [8.0, 0, 2, 2],
        })
        t = d.desglose_errores(datos, ["horizonte"]).iloc[0]
        self.assertAlmostEqual(t.mae_modelo, 5 / 4)
        self.assertAlmostEqual(t.mae_persistencia, 4 / 4)
        self.assertAlmostEqual(t.razon_mae, 1.25)
        c = d.concentracion_error(datos, n_distritos=1).set_index(["pronostico", "grupo"])
        self.assertAlmostEqual(c.loc[("modelo", "temporada_2023"), "fraccion_error_absoluto"], 4 / 5)
        self.assertAlmostEqual(c.loc[("modelo", "top1_distritos"), "fraccion_error_cuadratico"], 17 / 17)

    def test_curva_fiabilidad(self):
        c = d.curva_fiabilidad(np.array([0, 1, 1, 1]), np.array([0.05, 0.95, 0.92, 1.0]), 10)
        self.assertEqual(list(c.n), [1, 3])
        self.assertEqual(list(c.frecuencia_observada), [0.0, 1.0])


if __name__ == "__main__":
    unittest.main()
