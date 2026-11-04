"""Tests of phase 1b' (ERA5-Land humidity): definition of H, no leakage and the availability count."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase1b_prime as pb  # noqa: E402
from denguekay.features.climate import build_observed_climate  # noqa: E402


def _weekly(n=30, seed=0):
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2005-01-02", periods=n, freq="7D")
    return pd.concat([pd.DataFrame({"ubigeo": u, "semana_inicio": weeks, "hum_rel_media": rng.uniform(50, 90, n)})
                      for u in ("200101", "200104")], ignore_index=True)


def _origins(weekly):
    w = weekly.copy()
    return pd.DataFrame({"ubigeo": w.ubigeo, "origen_cierre": w.semana_inicio + pd.Timedelta(days=6)})


class TestDefinition(unittest.TestCase):
    def test_matches_gold_definition_at_the_h2_target(self):
        """H of origin week o equals build_observed_climate(h=2) on the row of target week o + 2."""
        weekly = _weekly()
        from denguekay.data.calendar import mmwr_epi_week

        cal = mmwr_epi_week(weekly.semana_inicio)
        panel = weekly.assign(anio=cal["anio_epi"].to_numpy(), semana=cal["semana_epi"].to_numpy())
        gold = build_observed_climate(panel, 2, variables=("hum_rel_media",))
        by_week = pb.humidity_by_origin_week(weekly)
        g = gold.assign(semana_origen=gold.semana_inicio - pd.Timedelta(days=14))
        both = g.merge(by_week, on=["ubigeo", "semana_origen"])
        np.testing.assert_array_equal(both["hum_rel_media_media5_h2"].to_numpy(), both.H.to_numpy())
        self.assertGreater(both.H.notna().sum(), 40)

    def test_no_leakage_by_perturbation(self):
        """G18: humidity of weeks after the origin week does not change H."""
        weekly = _weekly()
        origins = _origins(weekly)
        base = pb.add_humidity(origins, pb.humidity_by_origin_week(weekly))
        cut = pd.Timestamp("2005-03-27")
        altered = weekly.copy()
        later = altered.semana_inicio > cut
        altered.loc[later, "hum_rel_media"] = altered.loc[later, "hum_rel_media"] * 3 - 100
        other = pb.add_humidity(origins, pb.humidity_by_origin_week(altered))
        sel = origins.origen_cierre <= cut + pd.Timedelta(days=6)
        np.testing.assert_array_equal(base.loc[sel, pb.COLUMN].to_numpy(), other.loc[sel, pb.COLUMN].to_numpy())
        self.assertFalse(np.allclose(base.loc[~sel, pb.COLUMN].dropna(), other.loc[~sel, pb.COLUMN].dropna()))

    def test_extra_lag_and_publication(self):
        weekly = _weekly()
        origins = _origins(weekly)
        now = pb.add_humidity(origins, pb.humidity_by_origin_week(weekly))
        lagged = pb.add_humidity(origins, pb.humidity_by_origin_week(weekly, extra_lag=1))
        # with h=2 alignment the last week used ends on origen_cierre: published 5 days later
        self.assertEqual(pb.weeks_not_yet_published(now.dropna(subset=[pb.COLUMN])), now[pb.COLUMN].notna().sum())
        self.assertEqual(pb.weeks_not_yet_published(lagged.dropna(subset=[pb.COLUMN])), 0)
        u = lagged.ubigeo.eq("200101")
        np.testing.assert_array_equal(lagged.loc[u, pb.COLUMN].to_numpy()[1:], now.loc[u, pb.COLUMN].to_numpy()[:-1])

    def test_gaps_are_rejected(self):
        with self.assertRaises(ValueError):
            pb.humidity_by_origin_week(_weekly().drop(index=5))

    def test_g19(self):
        weekly = _weekly()
        out = pb.add_humidity(_origins(weekly), pb.humidity_by_origin_week(weekly))
        self.assertFalse(pb.guard_g19(out, since="2005-01-01")["pasa"])   # the first 4 weeks have no H
        self.assertTrue(pb.guard_g19(out, since="2005-02-05")["pasa"])


if __name__ == "__main__":
    unittest.main()
