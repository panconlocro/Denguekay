"""Tests of the phase 0 diagnosis of the model improvement study."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase0_diagnosis as d  # noqa: E402

HAS_DATA = d.V2_PREDICTIONS.exists() and d.SILVER_EPI_HISTORICAL.exists()


def _series(brote: list[int], ubigeo: str = "200101") -> pd.DataFrame:
    weeks = pd.date_range("2018-01-07", periods=len(brote), freq="7D")
    return pd.DataFrame({"ubigeo": ubigeo, "semana_inicio": weeks, "brote": brote})


class TestWeekStates(unittest.TestCase):
    def test_states_follow_the_definitions(self):
        brote = [0] * 10 + [1, 1, 1, 0, 0] + [0] * 9 + [1]
        st = d.week_states(_series(brote)).estado.tolist()
        self.assertEqual(st[:10], ["valle"] * 10)
        self.assertEqual(st[10:13], ["inicio_limpio", "inicio_limpio", "en_curso"])
        # Up to 8 weeks after the last brote week (indices 13..20) is the decay, then valley again.
        self.assertEqual(st[13:21], ["bajada"] * 8)
        self.assertEqual(st[21:24], ["valle"] * 3)
        # Only 11 weeks without brote before the last one: still a clean onset (>= 8).
        self.assertEqual(st[24], "inicio_limpio")

    def test_onset_after_a_short_pause_is_not_clean(self):
        brote = [0] * 10 + [1, 1] + [0] * 4 + [1, 1]
        st = d.week_states(_series(brote)).estado.tolist()
        self.assertEqual(st[16:18], ["en_curso", "en_curso"])

    def test_without_previous_history_the_first_onset_counts_as_clean(self):
        # episodes() gives inf weeks without outbreak to a district's first episode.
        st = d.week_states(_series([1, 1, 0])).estado.tolist()
        self.assertEqual(st, ["inicio_limpio", "inicio_limpio", "bajada"])


class TestCeilings(unittest.TestCase):
    def test_best_threshold_f1_matches_brute_force(self):
        rng = np.random.default_rng(3)
        y = rng.integers(0, 2, 300)
        p = np.round(rng.random(300) * 0.3 + 0.2 * y, 2)
        brute = max(2 * ((p >= t) & (y == 1)).sum() / ((p >= t).sum() + y.sum()) for t in np.unique(p))
        self.assertAlmostEqual(d.best_threshold_f1(y, p), brute)

    def test_oracles_recover_a_shifted_scale(self):
        rng = np.random.default_rng(5)
        y = rng.integers(0, 2, 2000)
        p = np.clip(0.05 + 0.3 * y + rng.normal(0, 0.05, 2000), 0, 1)  # well ordered, all below 0.50
        o = d.oracle_f1(y, p)
        self.assertGreater(o["f1_oraculo_isotonica"], 0.95)
        self.assertLessEqual(o["f1_oraculo_isotonica"], o["f1_mejor_umbral"] + 1e-12)

    def test_ece_is_zero_when_frequencies_match(self):
        y = np.array([0] * 9 + [1] + [0] * 5 + [1] * 5)
        p = np.array([0.1] * 10 + [0.5] * 10)
        self.assertAlmostEqual(d.expected_calibration_error(y, p), 0.0)


class TestPersistenceMargin(unittest.TestCase):
    def test_overlap_shares(self):
        data = pd.DataFrame({"horizonte": 2, "bloque": "temporada_2022", "brote": [1, 1, 1, 1, 0],
                             "probabilidad_calibrada": 0.3,
                             "alerta_050": [True, True, False, False, True],
                             "alerta_persistencia": [True, False, True, False, False]})
        r = d.persistence_margin(data).iloc[0]
        self.assertEqual(r.positivos, 4)
        self.assertEqual((r.ambos, r.solo_modelo, r.solo_persistencia, r.ninguno), (0.25, 0.25, 0.25, 0.25))
        self.assertEqual(r.recall_modelo_donde_persistencia_falla, 0.5)


class TestHistory(unittest.TestCase):
    def test_week_grid_has_mmwr_53_weeks_only_where_they_exist(self):
        g = d.week_grid(2014, 2016)
        self.assertEqual(g.groupby("anio").semana.max().to_dict(), {2014: 53, 2015: 52, 2016: 52})
        self.assertTrue(g.semana_inicio.dt.weekday.eq(6).all())

    @unittest.skipUnless(HAS_DATA, "Sin silver epi ni predicciones guardadas de la V2")
    def test_long_labels_equal_gold_from_2017(self):
        panel, series = d.panel_series()
        cases, audit = d.long_case_series(panel)
        self.assertEqual(audit["filas_solapadas_distintas"], 0)
        self.assertTrue(cases.ubigeo.str.fullmatch(r"\d{6}").all())
        labels = d.long_labels(cases)
        check = labels[labels.anio.ge(2017)].merge(series, on=["ubigeo", "anio", "semana"],
                                                   suffixes=("_l", "_g"), validate="one_to_one")
        self.assertEqual(len(check), len(series))
        self.assertTrue(check.brote_l.eq(check.brote_g).all())
        np.testing.assert_allclose(check.umbral_brote_casos_l, check.umbral_brote_casos_g, rtol=0, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
