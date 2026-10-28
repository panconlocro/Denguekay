"""Ablación climática: filas comparables y climatología por corte."""

import unittest

import numpy as np
import pandas as pd

from src.modeling.ablacion_clima import (
    agregar_anomalias_fold, preparar_filas_comunes, variantes_climaticas,
)
from tests.test_modeling_train import panel_sintetico


class AblacionClimaTests(unittest.TestCase):
    def test_variantes_y_arranque_iguales_en_ambos_horizontes(self):
        for h in (2, 4):
            with self.subTest(h=h):
                gold = panel_sintetico(h, periods=20)
                variantes = variantes_climaticas(h)
                self.assertEqual({k: len(v) for k, v in variantes.items()},
                                 {"base_6": 6, "mas_clima_observado": 8,
                                  "mas_anomalias": 8, "mas_ambos": 10})
                self.assertFalse({"brote", "casos_Dengue", "ubigeo"} &
                                 set().union(*map(set, variantes.values())))
                for col in variantes["mas_clima_observado"][-2:]:
                    gold[col] = gold.groupby("ubigeo").cumcount().ge(h + 4).astype(float)
                    gold.loc[gold.groupby("ubigeo").cumcount().lt(h + 4), col] = np.nan
                datos, excluidas = preparar_filas_comunes(gold, h)
                self.assertEqual(excluidas, 2 * (h + 4))
                self.assertEqual(len(datos), len(gold) - excluidas)
                gold.loc[gold.groupby("ubigeo").cumcount().eq(h + 6),
                         variantes["mas_clima_observado"][-1]] = np.nan
                with self.assertRaisesRegex(ValueError, "fuera del arranque"):
                    preparar_filas_comunes(gold, h)

    def test_anomalias_fold_no_cambian_por_clima_posterior_al_origen(self):
        gold = panel_sintetico(4, periods=120)
        silver = gold[["ubigeo", "anio", "semana", "semana_inicio"]].copy()
        posicion = silver.groupby("ubigeo").cumcount()
        silver["hum_rel_media"] = posicion.astype(float)
        silver["precip_total_mm"] = (posicion * 2).astype(float)
        train = gold.loc[gold.semana_inicio.ge(gold.semana_inicio.min() + pd.Timedelta(weeks=8)) &
                         gold.semana_inicio.lt(gold.semana_inicio.min() + pd.Timedelta(weeks=90))].copy()
        test = gold.loc[gold.semana_inicio.ge(gold.semana_inicio.min() + pd.Timedelta(weeks=90))].copy()
        corte = train.semana_inicio.max() + pd.Timedelta(days=6)
        antes_train, antes_test = agregar_anomalias_fold(train, test, silver, 4, corte)
        cambiado = silver.copy()
        # La semana objetivo 90 usa clima hasta 86. El cambio empieza
        # después del corte de ajuste y solo afecta orígenes posteriores.
        fecha_cambio = gold.semana_inicio.min() + pd.Timedelta(weeks=90)
        cambiado.loc[cambiado.semana_inicio.ge(fecha_cambio), "hum_rel_media"] += 1000
        despues_train, despues_test = agregar_anomalias_fold(train, test, cambiado, 4, corte)
        col = "hum_rel_media_anomalia_media5_h4"
        self.assertEqual(len(antes_test), len(test))
        self.assertFalse(antes_test[col].isna().any())
        pd.testing.assert_series_equal(antes_train[col], despues_train[col])
        primera = antes_test.semana_inicio.eq(antes_test.semana_inicio.min())
        pd.testing.assert_series_equal(antes_test.loc[primera, col],
                                       despues_test.loc[primera, col])
        self.assertFalse(antes_test[col].equals(despues_test[col]))


if __name__ == "__main__":
    unittest.main()
