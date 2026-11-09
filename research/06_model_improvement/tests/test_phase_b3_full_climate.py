"""Tests of variant b3 (full climate): temperature definition and no leakage (G31), availability, the raw NOAA
check (G34) and the adoption rule."""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase_b3_full_climate as b3  # noqa: E402
import preregistration as pr  # noqa: E402
from denguekay.data.calendar import mmwr_epi_week  # noqa: E402


def _weekly(n=30, seed=0):
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2005-01-02", periods=n, freq="7D")
    return pd.concat([pd.DataFrame({"ubigeo": u, "semana_inicio": weeks, "temp_media": rng.uniform(18, 32, n)})
                      for u in ("200101", "200202")], ignore_index=True)


def _origins(weekly):
    return pd.DataFrame({"ubigeo": weekly.ubigeo, "origen_cierre": weekly.semana_inicio + pd.Timedelta(days=6)})


class TestTemperature(unittest.TestCase):
    def test_definition_matches_the_gold_function(self):
        """G30 on synthetic data: the value of origin week o equals build_observed_climate(h=2) at o + 2."""
        weekly = _weekly()
        cal = mmwr_epi_week(weekly.semana_inicio)
        panel = weekly.assign(anio=cal["anio_epi"].to_numpy(), semana=cal["semana_epi"].to_numpy())
        g = b3.guard_temperature_definition(panel)
        self.assertTrue(g["pasa"])
        self.assertGreater(g["con_valor"], 40)

    def test_no_leakage_by_perturbation(self):
        """G31: temperature of weeks after the origin week does not change the variable."""
        weekly = _weekly()
        origins = _origins(weekly)
        base = b3.add_temperature(origins, b3.temperature_by_origin_week(weekly))
        cut = pd.Timestamp("2005-03-27")
        altered = weekly.copy()
        later = altered.semana_inicio > cut
        altered.loc[later, "temp_media"] = altered.loc[later, "temp_media"] * 2 - 40
        other = b3.add_temperature(origins, b3.temperature_by_origin_week(altered))
        sel = origins.origen_cierre <= cut + pd.Timedelta(days=6)
        np.testing.assert_array_equal(base.loc[sel, b3.TEMP_COLUMN].to_numpy(), other.loc[sel, b3.TEMP_COLUMN].to_numpy())
        self.assertFalse(np.allclose(base.loc[~sel, b3.TEMP_COLUMN].dropna(), other.loc[~sel, b3.TEMP_COLUMN].dropna()))

    def test_availability_and_coverage(self):
        weekly = _weekly()
        out = b3.add_temperature(_origins(weekly), b3.temperature_by_origin_week(weekly))
        g = b3.guard_temperature_availability(out)
        self.assertTrue(g["pasa"])   # Saturday + 7 days <= origen_cierre + 14
        self.assertEqual(b3.ERA5_LAND_DELAY_DAYS, 7)
        self.assertFalse(b3.guard_temperature_availability(out, reference_days=6)["pasa"])
        self.assertTrue(b3.guard_temperature_availability(out, reference_days=7)["pasa"])
        self.assertEqual(g["afectados_contra_origen_cierre"], g["origenes"])
        self.assertFalse(b3.guard_temperature_availability(out, reference_days=4)["pasa"])
        lagged = b3.add_temperature(_origins(weekly), b3.temperature_by_origin_week(weekly, extra_lag=1))
        self.assertEqual(b3.guard_temperature_availability(lagged, reference_days=0)["afectados"], 0)


class TestNoaaRaw(unittest.TestCase):
    RAW = ("YR MON  NINO1+2   ANOM   NINO3    ANOM   NINO4    ANOM NINO3.4    ANOM\n"
           "2026   9   24.90    4.10   28.10    3.00   29.80    1.10   29.20    2.50\n"
           "2026  10   26.12    5.25   29.24    4.16   29.88    1.20   30.01    3.25\n")

    def _check(self, silver_value):
        silver = pd.DataFrame({"anio": [2026], "mes": [10], "nino12_anom": [silver_value]})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sstoi.indices"
            path.write_text(self.RAW, encoding="utf-8")
            return b3.guard_raw_noaa(silver, raw_path=path)

    def test_value_matches(self):
        g = self._check(5.25)
        self.assertTrue(g["pasa"])
        self.assertEqual(g["crudo"], 5.25)

    def test_silver_differs(self):
        self.assertFalse(self._check(5.2)["pasa"])


class TestRule(unittest.TestCase):
    @staticmethod
    def v(*xs):
        return pd.DataFrame({"veredicto": list(xs)})

    def test_alert_or_count_without_a_loss_in_the_other(self):
        v = self.v
        self.assertTrue(pr.adopt_step_b3(v("gana", "gana", "empate"), v("empate", "empate", "empate")))
        self.assertTrue(pr.adopt_step_b3(v("empate", "empate", "empate"), v("gana", "gana", "empate")))
        self.assertFalse(pr.adopt_step_b3(v("compensa (empate)", "empate", "empate"), v("gana", "gana", "gana")))
        self.assertFalse(pr.adopt_step_b3(v("gana", "gana", "gana"), v("empate", "compensa (empate)", "empate")))
        self.assertFalse(pr.adopt_step_b3(v("gana", "gana", "empate"), v("pierde", "empate", "empate")))
        self.assertFalse(pr.adopt_step_b3(v("pierde", "empate", "empate"), v("gana", "gana", "gana")))
        self.assertFalse(pr.adopt_step_b3(v("gana", "empate", "empate"), v("gana", "empate", "empate")))
        self.assertFalse(pr.adopt_step_b3(v("empate", "empate", "empate"), v("empate", "empate", "empate")))

    def test_record(self):
        self.assertEqual(pr.STEP_B3_COLUMNS, ["hum_rel_media_media5_h2", "precip_total_mm_media5_h2",
                                              b3.TEMP_COLUMN, b3.NINO_COLUMN])
        self.assertEqual(pr.STEP_B3_TEMP_COLUMN, b3.TEMP_COLUMN)
        self.assertTrue(all(pd.Timestamp(d).dayofweek == 5 for d in pr.STEP_B3_COUNTERFACTUAL_ORIGINS))


if __name__ == "__main__":
    unittest.main()
