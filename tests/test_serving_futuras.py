"""Anti-fuga por valores y fechas usando semanas extraídas de gold real."""

import unittest

import numpy as np
import pandas as pd

from serving_soporte import leer_csv
from src.modeling.inferencia_futura import construir_filas_futuras
from src.modeling.validacion_temporal_compacta import variantes_compactas


class TestFilasFuturas(unittest.TestCase):
    def setUp(self):
        self.referencia = leer_csv("referencia_2017_muestra.csv")

    def construir(self, datos, h=2, **opciones):
        return construir_filas_futuras(datos, h, referencia=self.referencia, **opciones)

    def test_valores_futuros_iguales_a_gold_y_sin_fuga_temporal(self):
        for h in (2, 4):
            with self.subTest(h=h):
                panel = leer_csv(f"gold_temporal_h{h}_muestra.csv")
                columnas = variantes_compactas(h)["base_6_poblacion_2017"]
                filas, motivos = self.construir(panel, h, fecha_corte="2025-10-25")
                self.assertFalse(motivos)
                objetivo = pd.Timestamp("2025-10-19") + pd.Timedelta(weeks=h)
                esperado = panel.loc[panel.semana_inicio.eq(objetivo)].sort_values("ubigeo")
                np.testing.assert_allclose(filas[columnas], esperado[columnas], rtol=1e-12, atol=1e-12)
                self.assertTrue(filas.origen_cierre.eq(pd.Timestamp("2025-10-25")).all())
                # Alterar datos posteriores al origen no puede alterar los predictores.
                posterior = panel.semana_inicio.gt(pd.Timestamp("2025-10-19"))
                panel.loc[posterior, "casos_Dengue"] += 99999
                otras, _ = self.construir(panel, h, fecha_corte="2025-10-25")
                pd.testing.assert_frame_equal(filas, otras)

    def test_mmwr_cruza_2025_semana_53_sin_desplazar_el_objetivo(self):
        for h, semana, fecha in ((2, 1, "2026-01-04"), (4, 3, "2026-01-18")):
            filas, motivos = self.construir(leer_csv(f"gold_temporal_h{h}_muestra.csv"), h)
            self.assertEqual(len(filas), 3)
            self.assertFalse(motivos)
            self.assertTrue(filas.anio.eq(2026).all())
            self.assertTrue(filas.semana.eq(semana).all())
            self.assertTrue(filas.semana_inicio.eq(pd.Timestamp(fecha)).all())

    def test_cero_se_conserva_y_faltante_no_se_convierte_en_cero(self):
        panel = leer_csv("gold_temporal_h2_muestra.csv")
        filas, _ = self.construir(panel)
        origen = panel.loc[panel.semana.eq(52)].set_index("ubigeo")
        np.testing.assert_array_equal(filas.set_index("ubigeo").casos_lag_2, origen.casos_Dengue)
        self.assertTrue(filas.casos_lag_2.eq(0).any())
        ubigeo = origen.index[0]
        panel.loc[panel.ubigeo.eq(ubigeo) & panel.semana.eq(52), "casos_Dengue"] = np.nan
        filas, motivos = self.construir(panel)
        self.assertNotIn(ubigeo, set(filas.ubigeo))
        self.assertEqual(motivos[0]["ubigeo"], ubigeo)
        self.assertFalse(motivos[0]["disponible"])
        self.assertIn("historia", motivos[0]["motivo"])

    def test_origen_ausente_hueco_e_historia_insuficiente_no_generan_fila(self):
        panel = leer_csv("gold_temporal_h2_muestra.csv")
        for semana in (52, 50):
            datos = panel.loc[~(panel.ubigeo.eq("200101") & panel.semana.eq(semana))]
            filas, motivos = self.construir(datos)
            self.assertEqual(len(filas), 2)
            self.assertEqual(motivos[0]["ubigeo"], "200101")
        filas, motivos = self.construir(panel.loc[panel.semana.eq(52)])
        self.assertTrue(filas.empty)
        self.assertEqual(len(motivos), 3)

    def test_referencia_ausente_se_reporta_por_distrito(self):
        self.referencia = self.referencia.loc[~self.referencia.ubigeo.eq("200101")]
        filas, motivos = self.construir(leer_csv("gold_temporal_h2_muestra.csv"))
        self.assertEqual(len(filas), 2)
        self.assertIn("referencia", motivos[0]["motivo"])

    def test_validacion_de_panel_corte_columnas_y_horizonte(self):
        panel = leer_csv("gold_temporal_h2_muestra.csv")
        for opciones in ({"fecha_corte": "2025-10-24"}, {"fecha_corte": "2000-01-01"},
                         {"columnas": ["clima_futuro"]}):
            with self.subTest(opciones=opciones), self.assertRaises(ValueError):
                self.construir(panel, **opciones)
        with self.assertRaises(ValueError):
            self.construir(panel, 3)
        for datos in (panel.iloc[:0], pd.concat([panel, panel.iloc[:1]]),
                      panel.assign(ubigeo=panel.ubigeo.astype(int)), panel.assign(anio=2024)):
            with self.assertRaises(ValueError):
                self.construir(datos)

    def test_base_sin_censo_reutiliza_historia(self):
        panel = leer_csv("gold_temporal_h2_muestra.csv")
        filas, _ = construir_filas_futuras(panel, 2, columnas=variantes_compactas(2)["base_4"])
        self.assertEqual(len(filas), 3)
        self.assertNotIn("log_poblacion_censo_2017", filas)


if __name__ == "__main__":
    unittest.main()
