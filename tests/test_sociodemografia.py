"""Pruebas de rasgos censales fijos y PCA ajustado sin test."""

import unittest

import numpy as np
import pandas as pd

from src.modeling.sociodemografia import (
    ajustar_eje_urbano, construir_sociodemografia,
    construir_sociodemografia_anual, referencia_2017,
)


FRACCIONES = [
    "fraccion_rural", "fraccion_mujeres", "fraccion_menores_15",
    "fraccion_sin_seguro", "fraccion_analfabeta_15_mas",
    "fraccion_pared_precaria", "fraccion_piso_tierra", "fraccion_agua_red",
    "fraccion_agua_cisterna", "fraccion_desague_red",
    "fraccion_sin_saneamiento", "fraccion_alumbrado_red",
    "fraccion_hogares_refrigeradora", "fraccion_hogares_celular",
    "fraccion_hogares_lena",
]


def panel_sintetico() -> pd.DataFrame:
    fechas = pd.date_range("2017-01-01", periods=60, freq="W-SUN")
    filas = []
    for d in range(4):
        for i, fecha in enumerate(fechas):
            fila = {"ubigeo": f"20010{d+1}", "anio": 2017 + i // 52,
                    "semana": i % 52 + 1, "semana_inicio": fecha,
                    "poblacion": 1000 + 100 * d if i < 52 else 8000 + d}
            fila.update({c: 0.1 + 0.01 * (j + 1) * d if i < 52 else 0.9
                         for j, c in enumerate(FRACCIONES)})
            filas.append(fila)
    return pd.DataFrame(filas)


class SociodemografiaTests(unittest.TestCase):
    def setUp(self):
        self.panel = panel_sintetico()
        self.ref = referencia_2017(self.panel)

    def test_referencia_solo_2017_y_constante(self):
        self.assertEqual(len(self.ref), 4)
        self.assertEqual(self.ref.loc[self.ref.ubigeo.eq("200101"), "poblacion"].iloc[0], 1000)
        alterado = self.panel.copy()
        alterado.loc[alterado.anio.eq(2018), FRACCIONES + ["poblacion"]] = 0
        pd.testing.assert_frame_equal(self.ref, referencia_2017(alterado))

    def test_disponibilidad_segun_origen_para_dos_y_cuatro(self):
        for h in (2, 4):
            salida = construir_sociodemografia(self.panel, h, self.ref, "2018-01-01")
            distrito = salida.loc[salida.ubigeo.eq("200101")].reset_index(drop=True)
            self.assertEqual(len(salida), len(self.panel))
            self.assertTrue(distrito.iloc[:52 + h].log_poblacion_censo_2017.isna().all())
            self.assertAlmostEqual(distrito.loc[52 + h, "log_poblacion_censo_2017"], np.log(1000))
            self.assertAlmostEqual(distrito.loc[52 + h, "fraccion_rural_2017"], 0.1)
            self.assertFalse(any("_x" in c or "_y" in c for c in salida))
            retrospectivo = construir_sociodemografia(
                self.panel, h, self.ref, "2018-01-01",
                enmascarar_antes_disponibilidad=False,
            )
            primera = retrospectivo.loc[retrospectivo.ubigeo.eq("200101")].iloc[0]
            self.assertAlmostEqual(primera.log_poblacion_censo_2017, np.log(1000))

    def test_eje_se_ajusta_solo_con_distritos_entrenamiento(self):
        train = {"200101", "200102", "200103"}
        antes = ajustar_eje_urbano(self.ref, train)
        cambiado = self.ref.copy()
        cambiado.loc[cambiado.ubigeo.eq("200104"), FRACCIONES] = 0.999
        despues = ajustar_eje_urbano(cambiado, train)
        pd.testing.assert_series_equal(antes.media, despues.media)
        pd.testing.assert_series_equal(antes.desviacion, despues.desviacion)
        pd.testing.assert_series_equal(antes.cargas, despues.cargas)
        salida = construir_sociodemografia(self.panel, 2, self.ref, "2018-01-01", antes)
        self.assertTrue(np.isfinite(salida.eje_urbano_2017.dropna()).all())
        self.assertGreater(antes.varianza_explicada, 0)

    def test_errores_de_referencia(self):
        malo = self.panel.copy()
        malo.loc[1, "fraccion_rural"] = 0.999
        with self.assertRaisesRegex(ValueError, "cambia"):
            referencia_2017(malo)
        with self.assertRaisesRegex(ValueError, "sin correspondencia censal"):
            construir_sociodemografia(self.panel, 4, self.ref.iloc[1:], "2018-01-01")
        with self.assertRaisesRegex(ValueError, "duplicado"):
            construir_sociodemografia(self.panel, 4, pd.concat([self.ref, self.ref.iloc[[0]]]), "2018-01-01")
        incompleta = self.ref.copy()
        incompleta.loc[0, "fraccion_rural"] = np.nan
        with self.assertRaisesRegex(ValueError, "faltantes"):
            construir_sociodemografia(self.panel, 4, incompleta, "2018-01-01")

    def test_demografia_anual_se_repite_por_distrito_anio(self):
        eje = ajustar_eje_urbano(self.ref, {"200101", "200102", "200103"})
        salida = construir_sociodemografia_anual(self.panel, eje)
        self.assertEqual(len(salida), len(self.panel))
        self.assertFalse(salida.duplicated(["ubigeo", "anio", "semana"]).any())
        self.assertEqual(sum(c.endswith("_anual") for c in salida), 17)
        distrito = salida.loc[salida.ubigeo.eq("200101")].reset_index(drop=True)
        self.assertAlmostEqual(distrito.loc[0, "log_poblacion_anual"], np.log(1000))
        self.assertAlmostEqual(distrito.loc[52, "log_poblacion_anual"], np.log(8000))
        self.assertTrue(distrito.loc[:51, "eje_urbano_anual"].eq(distrito.loc[0, "eje_urbano_anual"]).all())
        self.assertTrue(distrito.loc[52:, "eje_urbano_anual"].eq(distrito.loc[52, "eje_urbano_anual"]).all())
        self.assertNotAlmostEqual(distrito.loc[0, "eje_urbano_anual"], distrito.loc[52, "eje_urbano_anual"])
        self.assertAlmostEqual(distrito.loc[52, "eje_urbano_anual"],
                               float(((pd.Series(0.9, index=eje.columnas) - eje.media) / eje.desviacion) @ eje.cargas))
        self.assertFalse(any(c.endswith(("_x", "_y")) for c in salida))

    def test_demografia_anual_refleja_extremo_futuro_y_valida_constancia(self):
        eje = ajustar_eje_urbano(self.ref, {"200101", "200102", "200103"})
        anterior = construir_sociodemografia_anual(self.panel, eje)
        cambiado = self.panel.copy()
        cambiado.loc[cambiado.anio.eq(2018), "fraccion_rural"] = 0.8
        posterior = construir_sociodemografia_anual(cambiado, eje)
        mascara = posterior.anio.eq(2018)
        self.assertFalse(anterior.loc[mascara, "fraccion_rural_anual"].equals(
            posterior.loc[mascara, "fraccion_rural_anual"]))
        self.assertTrue(anterior.loc[~mascara, "eje_urbano_anual"].equals(
            posterior.loc[~mascara, "eje_urbano_anual"]))
        invalido = self.panel.copy()
        invalido.loc[52, "fraccion_rural"] = 0.4
        with self.assertRaisesRegex(ValueError, "cambia entre semanas"):
            construir_sociodemografia_anual(invalido, eje)
        duplicado = pd.concat([self.panel, self.panel.iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "duplicadas"):
            construir_sociodemografia_anual(duplicado, eje)
        ausente = self.panel.drop(columns="fraccion_rural")
        with self.assertRaisesRegex(ValueError, "Faltan columnas"):
            construir_sociodemografia_anual(ausente, eje)


if __name__ == "__main__":
    unittest.main()
