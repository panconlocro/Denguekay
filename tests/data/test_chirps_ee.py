import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from denguekay.data.ingestion import chirps_ee as ce

TRANSFORM = (0.05, 0.0, -81.40, 0.0, -0.05, -4.00)


class TestMonthsAndBands(unittest.TestCase):
    def test_months_cover_2000_01_to_2026_09(self):
        m = ce.months()
        self.assertEqual((m[0], m[-1], len(m)), ("2000-01", "2026-09", 321))
        self.assertEqual(len(ce.month_days("2024-02")), 29)
        self.assertEqual(ce.band_name(date(2000, 1, 5)), "p20000105")


class TestLocalMean(unittest.TestCase):
    def test_coverage_is_the_fraction_of_each_pixel(self):
        from shapely.geometry import box

        whole = box(-81.40, -4.05, -81.35, -4.00)          # exactly pixel (0, 0)
        r, c, w = ce.coverage_weights(whole, TRANSFORM, (4, 4))
        self.assertEqual((r.tolist(), c.tolist()), ([0], [0]))
        self.assertAlmostEqual(w[0], 1.0)
        half = box(-81.375, -4.05, -81.325, -4.00)         # half of (0, 0) and half of (0, 1)
        r, c, w = ce.coverage_weights(half, TRANSFORM, (4, 4))
        self.assertEqual(sorted(zip(r.tolist(), c.tolist())), [(0, 0), (0, 1)])
        np.testing.assert_allclose(w, [0.5, 0.5])

    def test_polygon_outside_the_window_stops(self):
        from shapely.geometry import box

        with self.assertRaises(ValueError):
            ce.coverage_weights(box(-81.50, -4.05, -81.35, -4.00), TRANSFORM, (4, 4))

    def test_weighted_mean_ignores_no_data(self):
        data = np.array([[2.0, 4.0], [ce.NODATA, 8.0]], dtype="float32")
        rows, cols, w = np.array([0, 0, 1]), np.array([0, 1, 0]), np.array([1.0, 0.5, 1.0])
        self.assertAlmostEqual(ce.weighted_mean(data, rows, cols, w), (2 + 2) / 1.5)
        self.assertTrue(np.isnan(ce.weighted_mean(data, np.array([1]), np.array([0]), np.array([1.0]))))


class TestGuardChecks(unittest.TestCase):
    def test_grid_accepts_the_float32_rounded_origin_and_rejects_a_shift(self):
        chc = (0.05, 0.0, -81.3999985307455, 0.0, -0.05, -4.000000953674316)
        self.assertTrue(ce.check_grid(chc, [0.05, 0, -180, 0, -0.05, 50])["pasa"])
        self.assertFalse(ce.check_grid(chc, [0.05, 0, -179.975, 0, -0.05, 50])["pasa"])

    def test_pixels_must_match_within_tolerance_and_share_the_mask(self):
        a = np.array([[1.0, ce.NODATA]], dtype="float32")
        d = date(2000, 1, 1)
        self.assertTrue(ce.check_pixels({d: a}, {d: a.copy()})["pasa"])
        self.assertFalse(ce.check_pixels({d: a}, {d: a + np.array([[0.01, 0]], dtype="float32")})["pasa"])
        self.assertFalse(ce.check_pixels({d: a}, {d: np.array([[1.0, 0.0]], dtype="float32")})["pasa"])

    def test_polygon_means_use_abs_or_relative_tolerance(self):
        d = date(2000, 1, 1)
        local = pd.DataFrame({"ubigeo": ["200101", "200102"], "fecha": [d, d], "precip_mm": [0.0, 100.0]})
        ok = local.assign(precip_mm=[0.04, 101.9])
        self.assertTrue(ce.check_polygon_means(local, ok)["pasa"])
        bad = local.assign(precip_mm=[0.06, 100.0])
        self.assertFalse(ce.check_polygon_means(local, bad)["pasa"])
        missing = local.iloc[:1]
        self.assertFalse(ce.check_polygon_means(local, missing)["pasa"])


def response(month_days, ubigeos, value=1.0, null=None):
    feats = []
    for u in ubigeos:
        props = {"ubigeo": u}
        for d in month_days:
            props[ce.band_name(d)] = None if null == (u, d) else value
        feats.append({"type": "Feature", "geometry": None, "properties": props})
    return {"type": "FeatureCollection", "features": feats}


class TestDownload(unittest.TestCase):
    def test_month_parsing_flags_missing_days_and_nulls(self):
        days = ce.month_days("2000-02")
        r = response(days[:-1], ["200101", "200102"], null=("200102", days[0]))
        check = ce.check_month(r, "2000-02", ["200101", "200102", "200103"])
        self.assertEqual(check["distritos_faltantes"], ["200103"])
        self.assertEqual(check["dias_faltantes"], ["2000-02-29"])
        self.assertEqual(check["nulos"], [{"ubigeo": "200102", "fecha": "2000-02-01"}])

    def test_resumes_and_stops_at_the_first_error(self):
        calls = []

        def fetch(month):
            calls.append(month)
            if month == "2000-03":
                raise RuntimeError("Too many concurrent aggregations / quota")
            return response(ce.month_days(month), ["200101"]), []

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            ce.save_json(response(ce.month_days("2000-01"), ["200101"]), ce.month_path("2000-01", folder))
            s = ce.download_months(["2000-01", "2000-02", "2000-03", "2000-04"], fetch, ["200101"],
                                   folder=folder, log=lambda *_: None)
            self.assertEqual(calls, ["2000-02", "2000-03"])
            self.assertEqual((s["ya_estaban"], s["guardados"], s["estado"]),
                             (["2000-01"], ["2000-02"], "detenida_error"))
            self.assertFalse(ce.month_path("2000-03", folder).exists())
            saved = json.loads(ce.month_path("2000-02", folder).read_text(encoding="utf-8"))
            self.assertEqual(len(saved["features"]), 1)
            self.assertFalse(ce.save_json({}, ce.month_path("2000-02", folder)))

    def test_the_module_does_not_import_ee(self):
        import sys

        self.assertNotIn("ee", sys.modules)


if __name__ == "__main__":
    unittest.main()
