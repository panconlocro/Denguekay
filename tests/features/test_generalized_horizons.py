"""Generalización de horizontes: regresión contra gold y causalidad para h=1..6.

Las pruebas con datos reales se omiten si el silver o el gold no están en el
equipo (por ejemplo en CI, que solo tiene fixtures). Nada se escribe en data/.
"""

import json
import unittest

import numpy as np
import pandas as pd

from denguekay.features.climate import MAIN_CLIMATE
from denguekay.features.model_input_contract import predictor_families
from denguekay.features.outbreak_label import SeasonalOutbreakConfig
from denguekay.features.gold import HORIZONS, build_labels, build_gold
from denguekay.features.history_calendar import build_history_calendar
from denguekay.config.paths import GOLD, GOLD_MANIFEST, SILVER_EPI_HISTORICAL, SILVER_INTEGRATED
from denguekay.data.validation.forecast_contract import EXPERIMENTAL_HORIZONS

HAY_DATOS = SILVER_INTEGRATED.exists() and GOLD_MANIFEST.exists() and SILVER_EPI_HISTORICAL.exists()


def _panel_sintetico(semanas: int = 20) -> pd.DataFrame:
    fechas = pd.date_range("2022-01-02", periods=semanas, freq="7D")
    filas = []
    for k, ubigeo in enumerate(("200101", "200102")):
        for i, s in enumerate(fechas):
            filas.append({"ubigeo": ubigeo, "anio": 2022, "semana": i + 1,
                          "semana_inicio": s, "casos_Dengue": float((i * (k + 2)) % 7)})
    return pd.DataFrame(filas)


class TestHistoriaGeneralizada(unittest.TestCase):
    def test_causalidad_y_rezago_exacto_para_cada_h(self):
        panel = _panel_sintetico()
        for h in EXPERIMENTAL_HORIZONS:
            with self.subTest(h=h):
                hist = build_history_calendar(panel, h)
                con_origen = hist.dropna(subset=["origen_cierre"])
                self.assertTrue((con_origen.semana_inicio > con_origen.origen_cierre).all())
                self.assertTrue(((con_origen.semana_inicio - con_origen.origen_inicio).dt.days == 7 * h).all())
                esperado = panel.groupby("ubigeo").casos_Dengue.shift(h)
                pd.testing.assert_series_equal(hist[f"casos_lag_{h}"], esperado, check_names=False)

    def test_rechaza_horizontes_fuera_de_rango(self):
        for h in (0, 7):
            with self.assertRaisesRegex(ValueError, "entre 1 y 6"):
                build_history_calendar(_panel_sintetico(), h)
            with self.assertRaisesRegex(ValueError, "entre 1 y 6"):
                predictor_families(h)

    def test_gold_persistido_sigue_solo_en_2_y_4(self):
        self.assertEqual(HORIZONS, (2, 4))


@unittest.skipUnless(HAY_DATOS, "Requiere silver integrado, historia epi y gold locales")
class TestGoldGeneralizadoConDatos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from denguekay.data.loading import load_integrated

        cls.panel = load_integrated(SILVER_INTEGRATED)
        regla = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
        cls.config = SeasonalOutbreakConfig(
            multiplicador=regla["multiplicador"], anios_previos=regla["anios_previos"],
            minimo_casos=regla["minimo_casos"])
        cls.etiquetas = build_labels(cls.panel, cls.config)

    def test_regresion_reproduce_gold_actual_h2_h4(self):
        for h in HORIZONS:
            with self.subTest(h=h):
                archivo = GOLD / f"{SILVER_INTEGRATED.stem}_h{h}_gold.csv"
                disco = pd.read_csv(archivo, dtype={"ubigeo": "string"},
                                    parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"],
                                    float_precision="round_trip")
                memoria = build_gold(self.panel, h, self.etiquetas,
                                         min_outbreak_cases=self.config.minimo_casos)
                self.assertEqual(list(memoria.columns), list(disco.columns))
                pd.testing.assert_frame_equal(memoria.reset_index(drop=True), disco.reset_index(drop=True),
                                              check_dtype=False, check_exact=True)

    def test_causalidad_en_cada_h_con_perturbacion_del_futuro(self):
        corte = pd.Timestamp("2022-06-05")
        alterado = self.panel.copy()
        futuro = pd.to_datetime(alterado.semana_inicio) >= corte
        columnas = ["casos_Dengue", *[c for c in MAIN_CLIMATE if c in alterado]]
        rng = np.random.default_rng(7)
        for c in columnas:
            alterado.loc[futuro, c] = alterado.loc[futuro, c] + rng.integers(1, 50, futuro.sum())
        for h in EXPERIMENTAL_HORIZONS:
            with self.subTest(h=h):
                base = build_gold(self.panel, h)
                otro = build_gold(alterado, h)
                con_origen = base.dropna(subset=["origen_cierre"])
                self.assertTrue((con_origen.semana_inicio > con_origen.origen_cierre).all())
                # Filas cuyo origen cerró antes del corte: sus predictores no pueden cambiar.
                previas = base.origen_cierre.lt(corte)
                predictores = [c for c in base if c not in {"casos_Dengue", "origen_inicio", "origen_cierre"}
                               and pd.api.types.is_numeric_dtype(base[c])]
                pd.testing.assert_frame_equal(base.loc[previas, predictores], otro.loc[previas, predictores])
                # Y sí deben cambiar las del futuro (la prueba no es trivial).
                self.assertFalse(base.loc[~previas & base.origen_cierre.notna(), f"casos_lag_{h}"].equals(
                    otro.loc[~previas & otro.origen_cierre.notna(), f"casos_lag_{h}"]))


if __name__ == "__main__":
    unittest.main()
