"""Tests of the CHIRPS v3 ingestion and processing (no network: synthetic windows and a fake reader)."""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from rasterio.transform import from_origin

from denguekay.data.ingestion import chirps as ch
from denguekay.data.processing import chirps_precipitation as cp

# A 6x6 window of 0.05° pixels starting at lon -81.0, lat -5.0; the first column is sea (-9999).
TRANSFORM = from_origin(-81.0, -5.0, 0.05, 0.05)
DISTRICTS = pd.DataFrame({"id_distrito": [1, 2], "provincia": ["P", "P"], "distrito": ["A", "B"],
                          "lat": [-5.025, -5.175], "lon": [-80.925, -80.775]})


def _window(value=1.0, sea=True):
    data = np.full((6, 6), value, dtype="float32")
    if sea:
        data[:, 0] = ch.NODATA
    profile = {"driver": "GTiff", "dtype": "float32", "count": 1, "height": 6, "width": 6, "crs": "EPSG:4326",
               "transform": TRANSFORM, "nodata_declarado": None, "resolucion": (0.05, 0.05)}
    return data, profile


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class TestUrlsAndChecks(unittest.TestCase):
    def test_url_and_path(self):
        d = date(2000, 1, 5)
        self.assertEqual(ch.day_url(d), "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/sat/cogs/2000/"
                                        "chirps-v3.0.sat.2000.01.05.cog")
        self.assertEqual(ch.day_path(d, Path("x")), Path("x") / "2000" / "chirps-v3.0.sat.2000.01.05.tif")

    def test_check_window_detects_centroids_on_sea(self):
        data, profile = _window()
        ok = ch.check_window(data, profile, DISTRICTS)
        self.assertEqual((ok["centroides_sin_dato"], ok["pixeles_sin_dato"], ok["otros_negativos"]), ([], 6, 0))
        sea = DISTRICTS.assign(lon=[-80.975, -80.775])
        self.assertEqual(ch.check_window(data, profile, sea)["centroides_sin_dato"], ["A"])

    def test_sample_days_must_agree(self):
        good = ch.check_sample_days([date(2000, 1, 15), date(2025, 1, 15)], DISTRICTS, reader=lambda d: _window())
        self.assertTrue(good["ok"], good["problemas"])
        other_mask = lambda d: _window(sea=d.year == 2000)
        self.assertFalse(ch.check_sample_days([date(2000, 1, 15), date(2025, 1, 15)], DISTRICTS, reader=other_mask)["ok"])
        negative = lambda d: (_window()[0] - 5 * (d.year == 2025), _window()[1])
        self.assertFalse(ch.check_sample_days([date(2000, 1, 15), date(2025, 1, 15)], DISTRICTS, reader=negative)["ok"])


class TestSaveAndDownload(unittest.TestCase):
    def test_save_is_atomic_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2000" / "f.tif"
            self.assertTrue(ch.save_window(*_window(1.0), path))
            self.assertFalse(ch.save_window(*_window(9.0), path))
            import rasterio
            with rasterio.open(path) as dataset:
                self.assertEqual(float(dataset.read(1)[0, 1]), 1.0)
                self.assertEqual(float(dataset.read(1)[0, 0]), ch.NODATA)   # kept as it arrived
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def _run(self, reader, days=("2000-01-01", "2000-01-10"), **kwargs):
        clock = FakeClock()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name) / "final"
        summary = ch.download_final(*days, folder=folder, manifest_folder=Path(tmp.name), reader=reader,
                                    sleep=clock.sleep, clock=clock, progress_every=1000, **kwargs)
        return summary, folder, Path(tmp.name), clock

    def test_downloads_resumes_and_writes_a_manifest(self):
        summary, folder, root, _ = self._run(lambda d: _window())
        self.assertEqual((summary["estado"], summary["descargados"], summary["pendientes_al_final"]), ("completa", 10, 0))
        manifest = json.loads(Path(summary["manifiesto"]).read_text(encoding="utf-8"))
        for key in ("commit", "producto", "rango", "descargados", "fallidos", "inicio", "fin"):
            self.assertIn(key, manifest)
        calls = []
        again = ch.download_final("2000-01-01", "2000-01-10", folder=folder, manifest_folder=root,
                                  reader=lambda d: calls.append(d) or _window(), sleep=lambda s: None)
        self.assertEqual((calls, again["ya_existian"]), ([], 10))
        self.assertEqual(len(list(root.glob("manifiesto_final_*.json"))), 2)

    def test_429_waits_and_retries_the_same_day(self):
        hits = {"n": 0}

        def reader(d):
            if d == date(2000, 1, 3) and hits["n"] < 2:
                hits["n"] += 1
                raise ch.RateLimited("HTTP response code: 429")
            return _window()

        summary, _, _, clock = self._run(reader)
        self.assertEqual((summary["descargados"], summary["fallidos"]), (10, []))
        self.assertGreaterEqual(clock.t, ch.BACKOFF_START * 3)   # 120 s + 240 s of backoff

    def test_stops_after_several_429_in_a_row(self):
        def reader(d):
            if d >= date(2000, 1, 4):
                raise ch.RateLimited("429")
            return _window()

        summary, *_ = self._run(reader)
        self.assertEqual((summary["estado"], summary["descargados"]), ("detenida_429", 3))

    def test_other_errors_are_recorded_and_stop_after_several(self):
        def reader(d):
            raise OSError("timeout")

        summary, *_ = self._run(reader)
        self.assertEqual(summary["estado"], "detenida_errores")
        self.assertEqual(len(summary["fallidos"]), ch.MAX_CONSECUTIVE_ERRORS)

    def test_calibration_slows_down_and_stops_if_the_estimate_is_too_long(self):
        state = {"n": 0}

        def reader(d):   # a 429 after every 10 days
            state["n"] += 1
            if state["n"] % 11 == 0:
                raise ch.RateLimited("429")
            return _window()

        pacer = ch.Pacer(calibration_days=30)
        summary, *_ = self._run(reader, days=("2000-01-01", "2002-12-31"), pacer=pacer, max_hours=0.5)
        self.assertEqual(summary["estado"], "detenida_estimacion")
        self.assertGreater(pacer.pause, ch.INITIAL_PAUSE)
        self.assertIsNotNone(summary["calibracion"]["dias_por_minuto_antes_del_429"])
        quiet = ch.Pacer(calibration_days=5)
        ok, *_ = self._run(lambda d: _window(), pacer=quiet)
        self.assertEqual((ok["estado"], quiet.pause), ("completa", ch.INITIAL_PAUSE))


class TestProcessing(unittest.TestCase):
    def test_daily_values_with_sea_as_nan(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for i, d in enumerate(pd.date_range("2017-01-01", "2017-01-14")):
                data, profile = _window(float(i))
                data[2, 3] = ch.NODATA                      # district B's centroid is (3, 3): stays valid
                ch.save_window(data, profile, ch.day_path(d.date(), folder))
            sea = DISTRICTS.assign(lon=[-80.975, -80.775])  # district A on the sea column
            daily = cp.daily_from_bronze(folder, sea)
            self.assertEqual(len(daily), 28)
            self.assertTrue(daily[daily.id_distrito.eq(1)].precipitation_sum.isna().all())
            weekly = cp.weekly_precipitation(daily, sea)
            a, b = weekly[weekly.id_distrito.eq(1)], weekly[weekly.id_distrito.eq(2)]
            self.assertTrue(a.precip_total_mm.isna().all())                  # empty, not 0
            self.assertEqual(b.precip_total_mm.tolist(), [float(sum(range(7))), float(sum(range(7, 14)))])

    def test_publication_calendar_of_the_preliminary(self):
        saturdays = pd.Series(pd.to_datetime(["2017-01-07", "2017-01-14", "2017-01-28", "2017-02-25", "2017-02-26",
                                             "2016-12-31"]))
        official = pd.to_datetime(["2017-01-12", "2017-01-17", "2017-02-02", "2017-02-27", "2017-03-02",
                                   "2017-01-02"])   # CHC: the 2nd, 7th, 12th, 17th, 22nd and 27th
        self.assertEqual(cp.pentad_publication(saturdays, cp.OFFICIAL_LAG_DAYS).tolist(), official.tolist())
        conservative = official + pd.Timedelta(days=3)
        self.assertEqual(cp.PUBLICATION_LAG_DAYS, 5)
        self.assertEqual(cp.pentad_publication(saturdays).tolist(), conservative.tolist())

    def test_weekly_availability_and_guard(self):
        daily = pd.DataFrame({"id_distrito": 1, "time": pd.date_range("2017-01-01", "2017-01-14"),
                              "precipitation_sum": 1.0})
        weekly = cp.weekly_precipitation(daily, DISTRICTS)
        self.assertEqual(weekly.fecha_disponible.tolist(), pd.to_datetime(["2017-01-15", "2017-01-20"]).tolist())
        origins = pd.DataFrame({"origen_cierre": pd.to_datetime(["2017-01-15", "2017-01-15"]),
                                "semana_inicio": pd.to_datetime(["2017-01-01", "2017-01-08"])})
        self.assertEqual(cp.weeks_published_after(weekly, origins), 1)   # week of Jan 8 is usable from Jan 20

    def test_windows_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            ch.save_window(*_window(), ch.day_path(date(2017, 1, 1), folder))
            data, profile = _window()
            profile["transform"] = from_origin(-81.05, -5.0, 0.05, 0.05)
            ch.save_window(data, profile, ch.day_path(date(2017, 1, 2), folder))
            with self.assertRaises(ValueError):
                cp.daily_from_bronze(folder, DISTRICTS)


if __name__ == "__main__":
    unittest.main()
