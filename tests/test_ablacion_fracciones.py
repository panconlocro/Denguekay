"""Cobertura y comparación individual de fracciones censales y anuales."""

import unittest

import numpy as np
import pandas as pd

from src.modeling.ablacion_fracciones import (
    FRACCIONES, ganadora_por_temporada, opciones_grupo,
    preparar_fracciones, variantes_fracciones,
)
from tests.test_modeling_train import panel_sintetico


def ejemplo(h: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]:
    gold = panel_sintetico(h, periods=20)
    ref = pd.DataFrame({"ubigeo": ["200101", "200102"]})
    for j, c in enumerate(FRACCIONES):
        ref[c] = [0.10 + j * 0.01, 0.20 + j * 0.01]
        gold[f"{c}_anual"] = gold.ubigeo.map(dict(zip(ref.ubigeo, ref[c]))) + 0.01
    for c in ("fraccion_rural", "fraccion_menores_15", "fraccion_desague_red"):
        gold[f"{c}_2017"] = gold.ubigeo.map(dict(zip(ref.ubigeo, ref[c])))
    return gold, ref


class AblacionFraccionesTests(unittest.TestCase):
    def test_31_variantes_individuales_sin_objetivos(self):
        for h in (2, 4):
            with self.subTest(h=h):
                v = variantes_fracciones(h)
                self.assertEqual(len(v), 31)
                self.assertEqual(len(opciones_grupo(v, "fija")), 16)
                self.assertEqual(len(opciones_grupo(v, "anual")), 16)
                self.assertTrue(all(len(cols) == 7 for n, cols in v.items() if n != "base_6"))
                self.assertFalse({"brote", "casos_Dengue", "ubigeo", "umbral_brote_casos"} &
                                 set().union(*map(set, v.values())))

    def test_censo_fijo_no_cambia_con_fracciones_anuales(self):
        for h in (2, 4):
            gold, ref = ejemplo(h)
            original = gold.copy(deep=True)
            datos, excluidas = preparar_fracciones(gold, ref, h)
            self.assertEqual(excluidas, 2 * (h + 3))
            self.assertEqual(len(datos), len(gold) - excluidas)
            self.assertFalse(datos.duplicated(["ubigeo", "anio", "semana"]).any())
            pd.testing.assert_frame_equal(gold, original)
            cambiado = gold.copy()
            cambiado["fraccion_piso_tierra_anual"] += 0.1
            despues, _ = preparar_fracciones(cambiado, ref, h)
            pd.testing.assert_series_equal(datos.fraccion_piso_tierra_2017,
                                           despues.fraccion_piso_tierra_2017)
            self.assertFalse(datos.fraccion_piso_tierra_anual.equals(
                despues.fraccion_piso_tierra_anual))

    def test_rechaza_desajuste_nulos_y_duplicados(self):
        gold, ref = ejemplo()
        alterado = gold.copy()
        alterado.loc[10, "fraccion_rural_2017"] = 0.9
        with self.assertRaisesRegex(ValueError, "difieren"):
            preparar_fracciones(alterado, ref, 2)
        alterado = gold.copy()
        alterado.loc[10, "fraccion_rural_anual"] = np.nan
        with self.assertRaisesRegex(ValueError, "nulos"):
            preparar_fracciones(alterado, ref, 2)
        with self.assertRaisesRegex(ValueError, "duplicado"):
            preparar_fracciones(gold, pd.concat([ref, ref.iloc[[0]]]), 2)

    def test_ganadora_temporal_usa_solo_validacion(self):
        v = {"base_6": ["x"], "fija__a": ["x", "a"]}
        def fold(nombre: str, valor: float) -> dict:
            return {"bloque": nombre, "tipo": "validacion",
                    "regresion": {"alerta_derivada": {"f1": valor}},
                    "clasificacion": {"alerta_directa": {"f1": valor}}}
        base = [fold(f"temporada_{t}", 0.5) for t in (2021, 2022, 2023)]
        nueva = [fold("temporada_2021", 0.6), fold("temporada_2022", 0.4),
                 fold("temporada_2023", 0.6)]
        r = {"base_6": {"folds_validacion": base, "folds_prueba": [{"f1": 1.0}]},
             "fija__a": {"folds_validacion": nueva, "folds_prueba": [{"f1": 0.0}]}}
        ganadoras = ganadora_por_temporada(r, v, "clasificacion")
        self.assertEqual(ganadoras, {"temporada_2021": "fija__a",
                                     "temporada_2022": "base_6",
                                     "temporada_2023": "fija__a"})


if __name__ == "__main__":
    unittest.main()
