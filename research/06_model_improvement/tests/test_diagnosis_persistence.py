"""Tests of the read-only diagnosis against persistence."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import diagnosis_persistence as dp  # noqa: E402


def _rows():
    weeks = pd.date_range("2026-01-04", periods=10, freq="7D")
    cases = [0, 1, 4, 10, 20, 18, 9, 3, 1, 0]
    return pd.DataFrame({"ubigeo": "200101", "semana_inicio": weeks, "horizonte": 2, "bloque": "temporada_2026",
                         "casos_Dengue": cases, "persistencia": [0, 0, 1, 4, 10, 20, 18, 9, 3, 1],
                         "casos_modelo": np.array(cases) * 0.5, "casos_predichos": np.array(cases) * 0.75,
                         "brote": [0, 0, 0, 1, 1, 1, 1, 0, 0, 0], "umbral_brote_casos": 5.0,
                         "probabilidad_calibrada": [0.0, 0.1, 0.2, 0.6, 0.9, 0.9, 0.7, 0.3, 0.1, 0.0],
                         "alerta_persistencia": [False] * 5 + [True] * 3 + [False] * 2})


class TestDiagnosis(unittest.TestCase):
    def test_phase_bias_sign(self):
        t = dp.phase_errors(_rows())
        self.assertTrue((t.sesgo_modelo <= 0).all())       # μ = half the cases: never above
        rise = t[t.fase.eq("subida")].iloc[0]
        self.assertAlmostEqual(rise.suma_modelo_sobre_real, 0.5)
        self.assertGreater(rise.mae_persistencia, 0)

    def test_mixture_reading(self):
        d = _rows()
        w = pd.DataFrame({"horizonte": [2], "bloque": ["temporada_2026"], "w": [0.5]})
        r = dp.mixture_reading(d, w).iloc[0]
        self.assertAlmostEqual(r.razon_mae_w0, 1.0)
        mu, per, y = d.casos_modelo, d.persistencia, d.casos_Dengue
        self.assertAlmostEqual(r.razon_mae_w1, (mu - y).abs().mean() / (per - y).abs().mean())
        self.assertLessEqual(r.razon_mae_w_retrospectivo, min(r.razon_mae_w1, r.razon_mae_w_usado) + 1e-12)

    def test_onset_probabilities(self):
        d = _rows()
        lead = pd.DataFrame({"horizonte": [2], "bloque": ["temporada_2026"], "ubigeo": ["200101"],
                             "inicio": [d.semana_inicio[3]], "alerta_050": [2.0], "alerta_persistencia": [np.nan]})
        t = dp.onset_probabilities(d, lead)
        self.assertAlmostEqual(t.p_semana_inicio[0], 0.6)
        self.assertAlmostEqual(t.p_max_previas[0], 0.2)      # weeks 0..2 (inicio-4 is before the data)
        s = dp.onset_summary(t).iloc[0]
        self.assertEqual((s.avisados_050, s.avisados_persistencia, s.con_p_050_semana_inicio), (1, 0, 1))

    def test_calibration_in_large(self):
        r = dp.calibration_in_large(_rows()).iloc[0]
        self.assertAlmostEqual(r.tasa_observada, 0.4)
        self.assertAlmostEqual(r.prob_media, 0.38)
        self.assertAlmostEqual(r.prob_media_en_brote, 0.775)


if __name__ == "__main__":
    unittest.main()
