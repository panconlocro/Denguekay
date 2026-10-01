"""Variantes y ajuste por fold de la ablación sociodemográfica."""

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.modeling.ablacion_sociodemografica import (
    agregar_ejes_fold, validar_matriz_sociodemografica,
    variantes_sociodemograficas,
)
from src.modeling.sociodemografia import referencia_2017
from tests.test_modeling_train import panel_sintetico as gold_sintetico
from tests.test_sociodemografia import FRACCIONES, panel_sintetico as silver_sintetico


class AblacionSociodemograficaTests(unittest.TestCase):
    def test_variantes_no_usan_objetivo_y_columnas_reales(self):
        for h in (2, 4):
            with self.subTest(h=h):
                variantes = variantes_sociodemograficas(h)
                self.assertEqual(len(variantes), 10)
                self.assertEqual(len(variantes["base_6"]), 6)
                self.assertEqual(len(variantes["anual_15"]), 21)
                self.assertFalse({"casos_Dengue", "brote", "ubigeo",
                                  "umbral_brote_casos"} &
                                 set().union(*map(set, variantes.values())))

    def test_columna_anual_nula_falla_aunque_la_base_este_completa(self):
        h = 2
        datos = gold_sintetico(h, periods=20)
        datos = datos.loc[datos.groupby("ubigeo").cumcount().ge(h + 3)].copy()
        variantes = variantes_sociodemograficas(h)
        faltan = {c for cols in variantes.values() for c in cols
                  if not c.startswith("eje_urbano_")} - set(datos)
        for col in faltan:
            datos[col] = 0.5
        datos["socio_2017_disponible_al_origen"] = True
        validar_matriz_sociodemografica(datos, variantes)
        datos.loc[10, "fraccion_rural_anual"] = np.nan
        with self.assertRaisesRegex(ValueError, "incompletos"):
            validar_matriz_sociodemografica(datos, variantes)

    def test_pca_fijo_no_cambia_al_alterar_fracciones_anuales(self):
        silver = silver_sintetico()
        ref = referencia_2017(silver)
        filas = silver[["ubigeo", "anio", "semana", "semana_inicio"]].copy()
        filas["origen_cierre"] = filas.semana_inicio - pd.Timedelta(weeks=4) + pd.Timedelta(days=6)
        posicion = filas.groupby("ubigeo").cumcount()
        train = filas.loc[posicion.between(8, 41)].copy()
        test = filas.loc[posicion.between(46, 59)].copy()
        corte = test.origen_cierre.min()
        with patch("src.modeling.ablacion_sociodemografica.FECHA_SOCIO_2017", "2017-01-01"):
            antes_train, antes_test, varianza = agregar_ejes_fold(train, test, silver, ref, 4, corte)
            cambiado = silver.copy()
            cambiado.loc[cambiado.anio.eq(2018), FRACCIONES] = 0.7
            despues_train, despues_test, _ = agregar_ejes_fold(train, test, cambiado, ref, 4, corte)
        self.assertGreater(varianza, 0)
        self.assertEqual(len(antes_test), len(test))
        pd.testing.assert_series_equal(antes_train.eje_urbano_2017, despues_train.eje_urbano_2017)
        pd.testing.assert_series_equal(antes_test.eje_urbano_2017, despues_test.eje_urbano_2017)
        self.assertFalse(antes_test.eje_urbano_anual.equals(despues_test.eje_urbano_anual))


if __name__ == "__main__":
    unittest.main()
