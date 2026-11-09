"""Tests of phase 4 (Niño 1+2): availability at the origin, no leakage and the adoption rule."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import phase4_enso as p4  # noqa: E402
import preregistration as pr  # noqa: E402
from denguekay.data.processing.enso_index import with_availability  # noqa: E402


def _enso(n=24, start=2004):
    months = pd.period_range(f"{start}-01", periods=n, freq="M")
    data = pd.DataFrame({"anio": months.year, "mes": months.month, "nino12": 24.0,
                         "nino12_anom": np.arange(n, dtype=float)})
    return with_availability(data)


def _origins(dates):
    return pd.DataFrame({"ubigeo": "200101", "origen_cierre": pd.to_datetime(dates)})


class TestAvailability(unittest.TestCase):
    def test_last_available_month_and_mean_of_three(self):
        # 2004-03 is published on 2004-04-10: on 2004-04-10 it is usable, on 2004-04-09 only 2004-02 is
        out = p4.enso_at_origins(_origins(["2004-04-09", "2004-04-10", "2004-01-03"]), _enso())
        self.assertEqual(out.mes_usado.tolist()[:2], ["2004-02", "2004-03"])
        self.assertEqual(out.nino12_anom_ultimo.tolist()[:2], [1.0, 2.0])
        self.assertTrue(np.isnan(out.nino12_anom_media3.iloc[0]))   # only 2 months before 2004-03
        self.assertEqual(out.nino12_anom_media3.iloc[1], 1.0)       # mean of 0, 1, 2
        self.assertTrue(np.isnan(out.nino12_anom_ultimo.iloc[2]))   # nothing published yet
        self.assertTrue(p4.guard_g21(out.iloc[:2])["pasa"])

    def test_keeps_the_order_of_the_origins(self):
        dates = ["2005-06-04", "2004-05-01", "2005-01-01"]
        out = p4.enso_at_origins(_origins(dates), _enso())
        self.assertEqual(out.origen_cierre.tolist(), pd.to_datetime(dates).tolist())
        self.assertEqual(out.mes_usado.tolist(), ["2005-04", "2004-03", "2004-11"])

    def test_no_leakage_by_perturbation(self):
        """G22: months not yet published at an origin do not change its columns."""
        origins = _origins(pd.date_range("2004-06-05", "2005-10-29", freq="7D"))
        enso = _enso()
        base = p4.enso_at_origins(origins, enso)
        for cut in ("2004-09-18", "2005-03-05"):
            altered = enso.copy()
            later = altered.fecha_disponible > pd.Timestamp(cut)
            altered.loc[later, "nino12_anom"] = altered.loc[later, "nino12_anom"] * -7 + 3
            other = p4.enso_at_origins(origins, altered)
            sel = origins.origen_cierre <= pd.Timestamp(cut)
            pd.testing.assert_frame_equal(base.loc[sel, list(p4.COLUMNS)], other.loc[sel, list(p4.COLUMNS)])
            self.assertFalse(base.loc[~sel, "nino12_anom_ultimo"].equals(other.loc[~sel, "nino12_anom_ultimo"]))

    def test_guards_detect_problems(self):
        out = p4.enso_at_origins(_origins(["2006-01-07"]), _enso())
        self.assertTrue(p4.guard_g23(out)["pasa"])
        self.assertFalse(p4.guard_g21(out.assign(nino_fecha_disponible=pd.Timestamp("2006-02-10")))["pasa"])
        self.assertFalse(p4.guard_g23(out.assign(nino12_anom_media3=np.nan))["pasa"])

    def test_rejects_missing_months(self):
        with self.assertRaises(ValueError):
            p4.monthly_features(_enso().drop(index=5))


class TestPhase4Record(unittest.TestCase):
    def test_adoption(self):
        v = lambda *xs: pd.DataFrame({"horizonte": [2, 3, 4], "veredicto": list(xs)})
        self.assertTrue(pr.adopt_phase4(v("gana", "gana", "empate")))
        self.assertFalse(pr.adopt_phase4(v("gana", "gana", "pierde")))
        self.assertFalse(pr.adopt_phase4(v("gana", "empate", "empate")))
        self.assertEqual(set(pr.PHASE4_COLUMNS), {"4a", "4b"})
        self.assertEqual(set(sum(pr.PHASE4_COLUMNS.values(), [])), set(p4.COLUMNS))


if __name__ == "__main__":
    unittest.main()
