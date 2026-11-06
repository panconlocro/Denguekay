"""Tests of the CHIRPS v3 preliminary ingestion and the weekly silver (no network: fake responses, synthetic grids)."""

import tempfile
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

from denguekay.data.ingestion import chirps_prelim as cpr
from denguekay.data.processing import chirps_precipitation as cp

PIX = 0.05
GLOBAL_T = from_origin(-81.2, -4.8, PIX, PIX)          # a small stand-in for the global grid, 20 x 20
REF = {"transform": tuple(from_origin(-81.2 + 3 * PIX, -4.8 - 4 * PIX, PIX, PIX))[:6], "shape": (6, 5),
       "crs": rasterio.crs.CRS.from_epsg(4326), "dtype": "float32"}


def _write_global(path, transform=GLOBAL_T, seed=0):
    data = np.random.default_rng(seed).uniform(0, 30, (20, 20)).astype("float32")
    data[:, :2] = -9999
    with rasterio.open(path, "w", driver="GTiff", dtype="float32", count=1, height=20, width=20,
                       crs="EPSG:4326", transform=transform) as dst:
        dst.write(data, 1)
    return data, Path(path).read_bytes()


class FakeResponse:
    def __init__(self, status, content=b"", text="", headers=None):
        self.status_code, self.content, self.text = status, content, text
        self.headers = headers or {"Content-Length": str(len(content)), "Last-Modified": "Mon, 02 Nov 2026"}


class FakeClock:
    def __init__(self):
        self.t, self.slept = 0.0, []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


class ListingTest(unittest.TestCase):
    def test_parse_listing_and_days(self):
        html = ('<a href="chirps-v3.0.prelim.2026.09.30.tif">x</a> <a href="chirps-v3.0.prelim.2026.10.01.tif">x</a>'
                '<a href="chirps-v3.0.prelim.2026.10.02.tif">x</a><a href="other.tif">x</a>')
        listed = cpr.parse_listing(html)
        self.assertEqual(listed, [date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)])
        self.assertEqual(cpr.days_to_fetch(listed, date(2026, 10, 1)), [date(2026, 10, 1), date(2026, 10, 2)])
        self.assertEqual(cpr.days_to_fetch(listed, date(2026, 10, 5)), [])

    def test_gap_stops(self):
        with self.assertRaises(RuntimeError):
            cpr.days_to_fetch([date(2026, 10, 1), date(2026, 10, 3)], date(2026, 10, 1))
        with self.assertRaises(RuntimeError):
            cpr.days_to_fetch([date(2026, 10, 2)], date(2026, 10, 1))

    def test_status(self):
        with self.assertRaises(cpr.RateLimited):
            cpr.check_response(429)
        with self.assertRaises(RuntimeError):
            cpr.check_response(404)
        cpr.check_response(200)

    def test_pacer_keeps_sixty_seconds(self):
        clock = FakeClock()
        pacer = cpr.Pacer(sleep=clock.sleep, clock=clock)
        pacer.wait()
        clock.t += 5
        pacer.wait()
        clock.t += 70
        pacer.wait()
        self.assertEqual(clock.slept, [55.0])


class CropTest(unittest.TestCase):
    def test_crop_same_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, _ = _write_global(Path(tmp) / "g.tif")
            win, profile, grid = cpr.crop_to_reference(Path(tmp) / "g.tif", REF)
        self.assertTrue(grid["pasa"])
        np.testing.assert_allclose(grid["desfase_pixeles"], [3.0, 4.0], atol=1e-9)
        np.testing.assert_array_equal(win, data[4:10, 3:8])
        self.assertTrue(np.allclose(tuple(profile["transform"])[:6], REF["transform"]))

    def test_shifted_grid_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_global(Path(tmp) / "g.tif", transform=from_origin(-81.2 + 0.01, -4.8, PIX, PIX))
            with self.assertRaises(ValueError):
                cpr.crop_to_reference(Path(tmp) / "g.tif", REF)


class DownloadTest(unittest.TestCase):
    def test_stops_at_first_429_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as tmp_dl:
            _, content = _write_global(Path(tmp) / "g.tif")
            out = Path(tmp) / "prelim"
            answers = [FakeResponse(200, content), FakeResponse(429)]
            calls = []

            def get(url, **kw):
                calls.append(url)
                return answers.pop(0)

            clock = FakeClock()
            days = [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)]
            s = cpr.download_prelim(days, get=get, pacer=cpr.Pacer(sleep=clock.sleep, clock=clock),
                                    tmp_dir=Path(tmp_dl), ref=REF, folder=out, log=lambda *_: None)
            self.assertEqual(s["estado"], "detenida_429")
            self.assertEqual(len(calls), 2)
            self.assertEqual(clock.slept, [60.0])
            self.assertTrue(cpr.day_path(days[0], out).exists())
            self.assertFalse(cpr.day_path(days[1], out).exists())
            self.assertEqual(list(Path(tmp_dl).iterdir()), [])
            self.assertEqual(len(s["dias"][0]["sha256"]), 64)

            # resume: the saved day is skipped without a request
            answers[:] = [FakeResponse(200, content), FakeResponse(200, content)]
            calls.clear()
            s = cpr.download_prelim(days, get=get, pacer=cpr.Pacer(sleep=clock.sleep, clock=clock),
                                    tmp_dir=Path(tmp_dl), ref=REF, folder=out, log=lambda *_: None)
            self.assertEqual(s["estado"], "completa")
            self.assertEqual(s["ya_estaban"], ["2026-10-01"])
            self.assertEqual(len(calls), 2)

    def test_truncated_body_stops(self):
        with tempfile.TemporaryDirectory() as tmp_dl:
            bad = FakeResponse(200, b"abc", headers={"Content-Length": "10"})
            s = cpr.download_prelim([date(2026, 10, 1)], get=lambda *a, **k: bad, pacer=cpr.Pacer(sleep=lambda s: None),
                                    tmp_dir=Path(tmp_dl), ref=REF, folder=Path(tmp_dl) / "p", log=lambda *_: None)
        self.assertEqual(s["estado"], "detenida_error")


def _daily(days, version, value=1.0, ubigeos=("200101", "200202")):
    return pd.DataFrame([{"ubigeo": u, "fecha": d.date(), "precip_mm": value, "version": version}
                         for d in days for u in ubigeos])


class SilverTest(unittest.TestCase):
    def test_weeks_never_mix_versions(self):
        # 2026-09-20 and 2026-09-27 are Sundays; final ends 2026-09-30, preliminary from 2026-10-01
        final = _daily(pd.date_range("2026-09-20", "2026-09-30"), "final", 2.0)
        prelim = _daily(pd.date_range("2026-09-29", "2026-10-10"), "prelim", 1.0)
        daily = cp.combine_daily(final, prelim)
        self.assertEqual(daily[daily.fecha == date(2026, 9, 30)].version.unique().tolist(), ["final"])
        weekly, left_out = cp.weekly_by_version(daily)
        self.assertEqual(list(weekly.columns), cp.SILVER_COLUMNS)
        self.assertEqual(sorted(weekly.semana_inicio.unique()), ["2026-09-20", "2026-10-04"])
        self.assertEqual(left_out.semana_inicio.dt.strftime("%Y-%m-%d").unique().tolist(), ["2026-09-27"])
        row = weekly[weekly.semana_inicio == "2026-10-04"].iloc[0]
        self.assertEqual((row.version, row.precip_total_mm, row.fecha_disponible), ("prelim", 7.0, "2026-10-15"))
        self.assertEqual(weekly[weekly.semana_inicio == "2026-09-20"].precip_total_mm.tolist(), [14.0, 14.0])
        self.assertTrue(weekly.ubigeo.map(lambda u: isinstance(u, str) and len(u) == 6).all())

    def test_missing_value_keeps_nan(self):
        daily = _daily(pd.date_range("2026-09-20", "2026-09-26"), "final")
        daily.loc[0, "precip_mm"] = np.nan
        weekly, _ = cp.weekly_by_version(daily)
        self.assertEqual(weekly.precip_total_mm.isna().sum(), 1)

    def test_write_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            weekly, _ = cp.weekly_by_version(_daily(pd.date_range("2026-09-20", "2026-09-26"), "final"))
            path = cp.write_silver(weekly, Path(tmp) / "s.csv")
            back = pd.read_csv(path, dtype={"ubigeo": str})
            self.assertEqual(back.ubigeo.tolist(), ["200101", "200202"])
            with self.assertRaises(FileExistsError):
                cp.write_silver(weekly, path)


if __name__ == "__main__":
    unittest.main()
