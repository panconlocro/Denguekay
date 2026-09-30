"""Pruebas de valores y causalidad de las variables de la fase 2."""

import unittest

import numpy as np
import pandas as pd

from src.modeling.historia_calendario import construir_historia_calendario


class HistoriaCalendarioTests(unittest.TestCase):
    def setUp(self):
        fechas = pd.date_range("2020-12-06", periods=9, freq="W-SUN")
        semanas = [50, 51, 52, 53, 1, 2, 3, 4, 5]
        uno = pd.DataFrame({
            "ubigeo": "200101", "anio": [2020] * 4 + [2021] * 5,
            "semana": semanas, "semana_inicio": fechas,
            "casos_Dengue": [1, 2, 3, 4, 5, 6, 7, 8, 9],
        })
        dos = uno.assign(ubigeo="200102", casos_Dengue=np.arange(101, 110))
        self.panel = pd.concat([uno, dos], ignore_index=True)

    def test_dos_semanas_cruza_anio_y_no_cruza_distrito(self):
        f = construir_historia_calendario(self.panel, 2)
        a = f[f.ubigeo == "200101"].reset_index(drop=True)
        b = f[f.ubigeo == "200102"].reset_index(drop=True)
        self.assertTrue(a.iloc[:2]["casos_lag_2"].isna().all())
        self.assertEqual(a.iloc[4]["casos_lag_2"], 3)
        self.assertEqual(a.iloc[4]["casos_lag_3"], 2)
        self.assertTrue(pd.isna(a.iloc[4]["casos_media_4_h2"]))
        self.assertEqual(a.iloc[5]["casos_media_4_h2"], 2.5)
        self.assertEqual(a.iloc[5]["casos_semanas_positivas_4_h2"], 4)
        self.assertEqual(b.iloc[4]["casos_lag_2"], 103)
        self.assertEqual(a.iloc[4]["origen_inicio"], pd.Timestamp("2020-12-20"))

    def test_cuatro_semanas_solo_utiliza_observaciones_hasta_origen(self):
        f = construir_historia_calendario(self.panel, 4)
        a = f[f.ubigeo == "200101"].reset_index(drop=True)
        self.assertEqual(a.iloc[7]["casos_lag_4"], 4)
        self.assertEqual(a.iloc[7]["casos_lag_5"], 3)
        self.assertEqual(a.iloc[7]["casos_media_4_h4"], 2.5)
        self.assertEqual(a.iloc[7]["origen_cierre"], pd.Timestamp("2021-01-02"))

        alterado = self.panel.copy()
        alterado.loc[(alterado.ubigeo == "200101") &
                     (alterado.semana_inicio >= "2021-01-03"), "casos_Dengue"] = 999
        otro = construir_historia_calendario(alterado, 4)
        cols = [c for c in f if c.startswith("casos_")]
        pd.testing.assert_series_equal(f.iloc[7][cols], otro.iloc[7][cols])

    def test_cambios_despues_del_origen_no_alteran_ningun_horizonte(self):
        for h in (2, 4):
            with self.subTest(horizonte=h):
                base = construir_historia_calendario(self.panel, h)
                fila = base[(base.ubigeo == "200101") & (base.semana_inicio == "2021-01-24")].iloc[0]
                alterado = self.panel.copy()
                alterado.loc[(alterado.ubigeo == "200101") &
                             (alterado.semana_inicio > fila.origen_inicio), "casos_Dengue"] = 999
                nuevo = construir_historia_calendario(alterado, h)
                otra_fila = nuevo[(nuevo.ubigeo == "200101") &
                                  (nuevo.semana_inicio == "2021-01-24")].iloc[0]
                cols = [c for c in base if c.startswith("casos_")]
                pd.testing.assert_series_equal(fila[cols], otra_fila[cols])

    def test_calendario_conocido_y_semana_53(self):
        f = construir_historia_calendario(self.panel, 2)
        a = f[f.ubigeo == "200101"].reset_index(drop=True)
        self.assertAlmostEqual(a.iloc[3]["semana_epi_seno"], a.iloc[4]["semana_epi_seno"])
        self.assertAlmostEqual(a.iloc[3]["semana_epi_coseno"], a.iloc[4]["semana_epi_coseno"])
        self.assertTrue(np.isfinite(f["semana_epi_seno"]).all())

    def test_orden_de_entrada_no_cambia_resultado(self):
        esperado = construir_historia_calendario(self.panel, 4)
        mezclado = construir_historia_calendario(self.panel.sample(frac=1, random_state=11), 4)
        pd.testing.assert_frame_equal(esperado, mezclado)
        self.assertEqual(len(mezclado), len(self.panel))
        self.assertFalse(mezclado.duplicated(["ubigeo", "anio", "semana"]).any())

    def test_falla_con_casos_faltantes_o_hueco_semanal(self):
        faltante = self.panel.copy()
        faltante.loc[0, "casos_Dengue"] = np.nan
        with self.assertRaisesRegex(ValueError, "casos_Dengue"):
            construir_historia_calendario(faltante, 2)
        hueco = self.panel.drop(index=2)
        with self.assertRaisesRegex(ValueError, "huecos"):
            construir_historia_calendario(hueco, 2)


if __name__ == "__main__":
    unittest.main()
