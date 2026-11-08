"""Tests of the season 2026 evaluation helpers (synthetic data; no model is trained)."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase_2026 as p26  # noqa: E402
import preregistration as pr  # noqa: E402


class TestBlocksAndColumns(unittest.TestCase):
    def test_blocks_add_2026_and_later(self):
        names = [b for b, _, _ in p26.blocks()]
        self.assertEqual(names[-2:], ["temporada_2026", "posterior_2026"])
        self.assertIn(("posterior_2026", "temporada", 2027), p26.blocks())
        self.assertIn("calendario_2025", names)

    def test_variant_columns(self):
        cols = p26.variant_columns()
        self.assertEqual(set(cols), {"L + 5a", "b3", "d1", "d2"})
        self.assertEqual(cols["d2"], [*cols["d1"], "nino12_anom_media3"])
        self.assertFalse(any("nino" in c for c in cols["d1"]))
        self.assertEqual(len(cols["d1"]) - len(cols["L + 5a"]), 14)


class TestGuards(unittest.TestCase):
    def test_old_blocks_tolerance(self):
        saved = pd.DataFrame({"ubigeo": ["200101", "200101"], "semana_inicio": ["2010-01-03", "2010-01-10"],
                              "horizonte": 2, "bloque": "temporada_2010", "casos_predichos": [1.0, 2.0],
                              "probabilidad_brote": [0.1, 0.2]})
        new = pd.concat([saved.assign(casos_predichos=[1.0, 2.0 + 5e-7]),
                         saved.assign(bloque="temporada_2026")], ignore_index=True)
        self.assertTrue(p26.guard_old_blocks({17: new}, {17: saved})["pasa"])
        bad = new.assign(casos_predichos=[1.0, 2.01, 1.0, 2.0])
        self.assertFalse(p26.guard_old_blocks({17: bad}, {17: saved})["pasa"])


class TestReadings(unittest.TestCase):
    def test_prelim_origins_count_window_weeks(self):
        chirps = pd.DataFrame({"semana_inicio": pd.to_datetime(["2026-09-20", "2026-09-27", "2026-10-04"]),
                               "version": ["final", "prelim", "prelim"]})
        pred = pd.DataFrame({"bloque": "posterior_2026", "origen_cierre": pd.to_datetime(["2026-09-26", "2026-10-03",
                                                                                         "2026-10-10"])})
        out = p26.prelim_origins(None, chirps, pred, ["posterior_2026"])
        self.assertEqual(out.b3_semanas_prelim.tolist(), [0, 1, 2])
        self.assertEqual(out.d_semanas_prelim.tolist(), [0, 1, 2])

    def test_loso_calibration_never_uses_the_evaluated_season(self):
        rng = np.random.default_rng(0)
        rows = []
        for block in ("fuera_2010", "fuera_2015", "fuera_2016"):
            n = 200
            y = rng.integers(0, 2, n)
            rows.append(pd.DataFrame({"horizonte": 2, "bloque": block, "brote": y, "probabilidad_brote": rng.uniform(0, 1, n),
                                      "casos_predichos": rng.uniform(0, 10, n), "persistencia": rng.uniform(0, 10, n),
                                      "casos_Dengue": rng.uniform(0, 10, n), "umbral_brote_casos": 5.0}))
        data = pd.concat(rows, ignore_index=True)
        out = p26.loso_calibrate_and_mix(data)
        changed = data.copy()
        changed.loc[changed.bloque.eq("fuera_2010"), "brote"] = 1 - changed.loc[changed.bloque.eq("fuera_2010"), "brote"]
        out2 = p26.loso_calibrate_and_mix(changed)
        sel = data.bloque.eq("fuera_2010")
        np.testing.assert_array_equal(out.loc[sel, "probabilidad_calibrada"], out2.loc[sel, "probabilidad_calibrada"])
        self.assertFalse(np.allclose(out.loc[~sel, "probabilidad_calibrada"], out2.loc[~sel, "probabilidad_calibrada"]))

    def test_onset_auprc_with_floor_two(self):
        import phase_d_weather_windows as pdw

        data = pd.DataFrame({"horizonte": 2, "bloque": "temporada_2026", "brote": [0, 1, 0, 1],
                             "probabilidad_calibrada": [0.1, 0.9, 0.2, 0.6], "persistencia": [0.0, 1.0, 3.0, 0.0],
                             "umbral_brote_casos": [0.0, 0.0, 5.0, 0.5]})
        clim = pd.Series(0.5, index=data.index)
        literal = pdw.reported_metrics(data, clim, ["temporada_2026"]).iloc[0]
        floored = pdw.reported_metrics(data, clim, ["temporada_2026"], floor=2.0).iloc[0]
        self.assertEqual((literal.n_bajo_umbral, floored.n_bajo_umbral), (2, 4))

    def test_rule_constants(self):
        self.assertEqual(pr.SEASON_2026_DECIDING, (2010, 2015, 2016, 2022, 2023, 2026))
        self.assertEqual(p26.LOSO_SEASONS, (2010, 2015, 2016, 2017, 2022, 2023, 2024, 2026))


if __name__ == "__main__":
    unittest.main()
