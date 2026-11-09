"""Tests of the long-history matrices of phase 1a (guards G1 and G4)."""

import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase0_diagnosis as d  # noqa: E402
import phase1_history as p1  # noqa: E402
import preregistration as pr  # noqa: E402

HAS_DATA = d.V2_PREDICTIONS.exists() and d.SILVER_EPI_HISTORICAL.exists()


def _cases(seed: int = 0, first: int = 2000, last: int = 2007) -> pd.DataFrame:
    grid = d.week_grid(first, last)
    rng = np.random.default_rng(seed)
    parts = []
    for u in ("200101", "200102", "200103"):
        g = grid.assign(ubigeo=u)
        g["casos_Dengue"] = rng.poisson(rng.uniform(0.2, 3), len(g)) * rng.integers(0, 2, len(g))
        parts.append(g)
    return pd.concat(parts, ignore_index=True)[["ubigeo", "anio", "semana", "semana_inicio", "casos_Dengue"]]


def _origins(cases: pd.DataFrame) -> pd.DataFrame:
    labels = d.long_labels(cases)
    matrices = p1.long_matrices(cases, labels)
    return p1.long_origins(cases, matrices[2])


class TestNoLeakage(unittest.TestCase):
    """G4: perturbing cases after an origin does not change that origin's variables."""

    def test_perturbation_after_the_origin(self):
        cases = _cases()
        base = _origins(cases)
        cut = pd.Timestamp("2006-06-04")
        altered = cases.copy()
        later = altered.semana_inicio.ge(cut)
        altered.loc[later, "casos_Dengue"] = altered.loc[later, "casos_Dengue"] * 7 + 13
        other = _origins(altered)
        key = ["ubigeo", "origen_cierre"]
        before = lambda o: o[o.origen_cierre.lt(cut)].set_index(key)[p1.V1_COLUMNS].sort_index()
        a, b = before(base), before(other)
        self.assertGreater(len(a), 200)  # 3 districts x 76 origin weeks
        pd.testing.assert_frame_equal(a, b)
        # The perturbation does reach the origins after the cut (the test is not vacuous).
        after = lambda o: o[o.origen_cierre.ge(cut + pd.Timedelta(weeks=1))].set_index(key)["hist_lag_a"]
        self.assertFalse(after(base).equals(after(other)))

    def test_origins_start_with_labels_and_full_history(self):
        o = _origins(_cases())
        self.assertGreaterEqual(o.semana_inicio.min(), pd.Timestamp("2005-01-02"))
        self.assertFalse(o[p1.V1_COLUMNS].isna().any().any())
        self.assertTrue(o.origen_cierre.lt(o.semana_inicio).all())


class TestWeeksSinceLastCase(unittest.TestCase):
    def test_recompute_matches_b3(self):
        cases = _cases(seed=3)
        o = _origins(cases)
        expected = p1.weeks_since_last_case(cases, o.ubigeo, o.origen_cierre - pd.Timedelta(days=6))
        np.testing.assert_array_equal(o.propia_semanas_desde_ultimo_caso.to_numpy(), expected)


class TestBlocks(unittest.TestCase):
    def test_seasonal_blocks(self):
        b = p1.seasonal_blocks(2008)
        self.assertEqual(b[0], ("temporada_2008", "temporada", 2008))
        self.assertEqual(b[-2], ("temporada_2024", "temporada", 2024))
        self.assertEqual(b[-1], ("calendario_2025", "calendario", 2025))


@unittest.skipUnless(HAS_DATA, "Sin datos")
class TestG1(unittest.TestCase):
    def test_long_origins_match_v1_with_the_amendment(self):
        from denguekay.config.paths import GOLD_MANIFEST
        from denguekay.evaluation import variants as fh
        from denguekay.model import frozen_configs as cf

        panel = d.load_integrated()
        cases, _ = d.long_case_series(panel)
        labels = d.long_labels(cases)
        origins = p1.long_origins(cases, p1.long_matrix(cases, labels, 2))
        rule = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
        v1 = cf.origins(panel, fh.inputs(panel, rule), rule, configuration=cf.CONFIG_2026_V1)
        g1 = p1.compare_origins(origins, v1, exception=pr.G1_EXCEPTION, cases=cases)
        self.assertTrue(g1["pasa"], g1)
        self.assertEqual(g1["excepcion_G1"]["filas"], 134)


if __name__ == "__main__":
    unittest.main()
