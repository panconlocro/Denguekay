"""Tests of climate step b (CHIRPS rainfall): definition, no leakage (G26), availability (G27) and coverage."""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase_b_rain as pbr  # noqa: E402
import preregistration as pr  # noqa: E402
from denguekay.data.calendar import mmwr_epi_week  # noqa: E402
from denguekay.features.climate import build_observed_climate  # noqa: E402


def _weekly(n=30, seed=0, lag_days=5):
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2005-01-02", periods=n, freq="7D")
    published = weeks + pd.Timedelta(days=6 + lag_days)
    return pd.concat([pd.DataFrame({"ubigeo": u, "semana_inicio": weeks, "precip_total_mm": rng.gamma(0.8, 10, n),
                                    "version": "final", "fecha_disponible": published})
                      for u in ("200101", "200202")], ignore_index=True)


def _origins(weekly):
    return pd.DataFrame({"ubigeo": weekly.ubigeo, "origen_cierre": weekly.semana_inicio + pd.Timedelta(days=6)})


class TestDefinition(unittest.TestCase):
    def test_matches_gold_definition_at_the_h2_target(self):
        """The variable of origin week o equals build_observed_climate(h=2) on the row of target week o + 2."""
        weekly = _weekly()
        cal = mmwr_epi_week(weekly.semana_inicio)
        panel = weekly.assign(anio=cal["anio_epi"].to_numpy(), semana=cal["semana_epi"].to_numpy())
        gold = build_observed_climate(panel, 2, variables=("precip_total_mm",))
        by_week = pbr.rain_by_origin_week(weekly)
        g = gold.assign(semana_origen=gold.semana_inicio - pd.Timedelta(days=14))
        both = g.merge(by_week, on=["ubigeo", "semana_origen"])
        np.testing.assert_array_equal(both[pbr.COLUMN].to_numpy(), both.R.to_numpy())
        self.assertGreater(both.R.notna().sum(), 40)

    def test_no_leakage_by_perturbation(self):
        """G26: rainfall of weeks after the origin week does not change the variable."""
        weekly = _weekly()
        origins = _origins(weekly)
        base = pbr.add_rain(origins, pbr.rain_by_origin_week(weekly))
        cut = pd.Timestamp("2005-03-27")
        altered = weekly.copy()
        later = altered.semana_inicio > cut
        altered.loc[later, "precip_total_mm"] = altered.loc[later, "precip_total_mm"] * 5 + 100
        other = pbr.add_rain(origins, pbr.rain_by_origin_week(altered))
        sel = origins.origen_cierre <= cut + pd.Timedelta(days=6)
        np.testing.assert_array_equal(base.loc[sel, pbr.COLUMN].to_numpy(), other.loc[sel, pbr.COLUMN].to_numpy())
        self.assertFalse(np.allclose(base.loc[~sel, pbr.COLUMN].dropna(), other.loc[~sel, pbr.COLUMN].dropna()))

    def test_gaps_are_rejected(self):
        with self.assertRaises(ValueError):
            pbr.rain_by_origin_week(_weekly().drop(index=5))

    def test_read_keeps_ubigeo_as_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.csv"
            w = _weekly(n=6).assign(ubigeo=lambda d: d.ubigeo.str.replace("200101", "000101"))
            w.to_csv(path, index=False)
            back = pbr.read_chirps(path)
        self.assertIn("000101", set(back.ubigeo))


class TestAvailability(unittest.TestCase):
    def test_on_time_and_late_weeks(self):
        weekly = _weekly(lag_days=10)
        out = pbr.add_rain(_origins(weekly), pbr.rain_by_origin_week(weekly))
        g = pbr.guard_availability(out)
        self.assertTrue(g["pasa"])
        self.assertEqual(g["margen_minimo_dias"], 4)
        self.assertEqual(g["afectados_contra_origen_cierre"], g["origenes_con_lluvia"])

        late = weekly.copy()
        late.loc[late.semana_inicio == pd.Timestamp("2005-03-06"), "fecha_disponible"] += pd.Timedelta(days=20)
        out = pbr.add_rain(_origins(late), pbr.rain_by_origin_week(late))
        g = pbr.guard_availability(out)
        self.assertFalse(g["pasa"])
        self.assertEqual(g["afectados"], 2 * 3)   # origin weeks 03-06, 03-13 and 03-20 (later ones have margin)

    def test_the_latest_week_of_the_window_counts(self):
        """A late week earlier in the window still blocks the origin (the maximum over the 5 weeks is used)."""
        weekly = _weekly(lag_days=5)
        weekly.loc[weekly.semana_inicio == pd.Timestamp("2005-03-06"), "fecha_disponible"] += pd.Timedelta(days=40)
        out = pbr.add_rain(_origins(weekly), pbr.rain_by_origin_week(weekly))
        self.assertEqual(pbr.guard_availability(out)["afectados"], 2 * 5)   # every origin whose window holds it

    def test_coverage(self):
        weekly = _weekly()
        out = pbr.add_rain(_origins(weekly), pbr.rain_by_origin_week(weekly))
        self.assertFalse(pbr.guard_coverage(out, since="2005-01-01")["pasa"])   # the first 4 weeks have none
        self.assertTrue(pbr.guard_coverage(out, since="2005-02-05")["pasa"])
        self.assertEqual(pbr.versions_used(out, weekly), {"final": len(out) - 8})


class TestPreregistration(unittest.TestCase):
    def test_variants_and_rule(self):
        self.assertEqual(pr.STEP_B_COLUMNS["b1"], [pbr.COLUMN])
        self.assertEqual(pr.STEP_B_COLUMNS["b2"], [pr.PHASE1B_PRIME_COLUMN, pbr.COLUMN])
        self.assertEqual(pr.STEP_B_REFERENCE_DAYS, pbr.REFERENCE_DAYS)
        v = lambda *xs: pd.DataFrame({"veredicto": list(xs)})  # noqa: E731
        self.assertTrue(pr.adopt_step_b(v("gana", "gana", "empate")))
        self.assertFalse(pr.adopt_step_b(v("gana", "empate", "empate")))
        self.assertFalse(pr.adopt_step_b(v("gana", "gana", "compensa (empate)")))
        self.assertFalse(pr.adopt_step_b(v("gana", "gana", "pierde")))


if __name__ == "__main__":
    unittest.main()
