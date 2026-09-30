"""Pruebas de calendario, corte y ausencia de clima futuro."""

import unittest

import numpy as np
import pandas as pd

from src.modeling.clima import ajustar_climatologia, construir_clima


def panel_ejemplo() -> pd.DataFrame:
    fechas = pd.date_range("2019-12-29", periods=112, freq="W-SUN")
    filas = []
    for distrito, extra in (("200101", 0), ("200102", 10)):
        for i, fecha in enumerate(fechas):
            filas.append({"ubigeo": distrito, "anio": int(fecha.year),
                          "semana": i % 52 + 1, "semana_inicio": fecha,
                          "hum_rel_media": float(i + extra),
                          "precip_total_mm": float(i * 2 + extra),
                          "temp_min": float(i / 10 + extra),
                          "lluvia_total_mm": float(i * 2 + extra)})
    return pd.DataFrame(filas)


class ClimaFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.panel = panel_ejemplo()
        self.corte = pd.Timestamp("2020-12-26")

    def test_ventana_h4_y_h2_acaba_en_origen(self):
        modelo = ajustar_climatologia(self.panel, self.corte)
        for h in (2, 4):
            salida = construir_clima(self.panel, h, modelo)
            fila = salida.loc[salida.ubigeo.eq("200101")].iloc[65]
            self.assertEqual(fila[f"hum_rel_media_media5_h{h}"],
                             np.mean(np.arange(65 - h - 4, 65 - h + 1)))
            origen = self.panel.loc[65 - h - 4:65 - h].copy()
            origen["semana_clima"] = origen.semana.clip(upper=52)
            referencia = origen.merge(modelo.tabla, on=["ubigeo", "semana_clima"],
                                      suffixes=("", "_clima"), validate="many_to_one")
            esperado_anomalia = (referencia.hum_rel_media - referencia.hum_rel_media_clima).mean()
            self.assertAlmostEqual(fila[f"hum_rel_media_anomalia_media5_h{h}"],
                                   esperado_anomalia)
            self.assertTrue(salida.loc[salida.ubigeo.eq("200101")].iloc[:h + 4][
                f"hum_rel_media_media5_h{h}"].isna().all())
            self.assertEqual(len(salida), len(self.panel))
            self.assertFalse(any("lluvia_total_mm" in c for c in salida))

    def test_climatologia_no_mira_despues_del_corte(self):
        base = ajustar_climatologia(self.panel, self.corte)
        cambiado = self.panel.copy()
        cambiado.loc[cambiado.semana_inicio.gt(self.corte), "hum_rel_media"] += 10000
        nueva = ajustar_climatologia(cambiado, self.corte)
        pd.testing.assert_frame_equal(base.tabla, nueva.tabla)

    def test_cambio_posterior_al_origen_no_altera_feature(self):
        modelo = ajustar_climatologia(self.panel, self.corte)
        antes = construir_clima(self.panel, 4, modelo)
        cambiado = self.panel.copy()
        cambiado.loc[(cambiado.ubigeo == "200101") & (cambiado.semana_inicio >=
                      self.panel.loc[65, "semana_inicio"] - pd.Timedelta(weeks=3)),
                     "precip_total_mm"] = 99999
        despues = construir_clima(cambiado, 4, modelo)
        pd.testing.assert_series_equal(antes.iloc[65], despues.iloc[65])

    def test_anomalia_de_semana_53_usa_casilla_52(self):
        panel = self.panel.copy()
        panel.loc[52, "semana"] = 53
        modelo = ajustar_climatologia(panel, "2021-01-02")
        fila = modelo.tabla.loc[(modelo.tabla.ubigeo == "200101") &
                                (modelo.tabla.semana_clima == 52)].iloc[0]
        self.assertEqual(fila.hum_rel_media,
                         panel.loc[[51, 52], "hum_rel_media"].mean())

    def test_panel_duplicado_o_incompleto_falla(self):
        with self.assertRaisesRegex(ValueError, "duplicadas"):
            ajustar_climatologia(pd.concat([self.panel, self.panel.iloc[[0]]]), self.corte)
        with self.assertRaisesRegex(ValueError, "completa"):
            p = self.panel.copy()
            p.loc[0, "hum_rel_media"] = np.nan
            ajustar_climatologia(p, self.corte)
        with self.assertRaisesRegex(ValueError, "sin historia"):
            ajustar_climatologia(self.panel, "2020-01-04")


if __name__ == "__main__":
    unittest.main()
