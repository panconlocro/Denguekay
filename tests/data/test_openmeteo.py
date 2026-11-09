"""Tests of the configurable date range and model of the Open-Meteo download (no network)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from denguekay.config.paths import CACHE_METEO
from denguekay.data.ingestion import openmeteo as om


def _response(columns=None):
    daily = {c: [1.0, 2.0] for c in (columns or om.DAILY_VARS)}
    daily["time"] = ["2017-01-01", "2017-01-02"]
    r = MagicMock(status_code=200)
    r.json.return_value = {"daily": daily}
    return r


class TestFetchDistrict(unittest.TestCase):
    def test_default_sends_no_models_and_keeps_the_range(self):
        with patch.object(om.requests, "get", return_value=_response()) as get:
            om.fetch_district(-5.0, -80.0)
        params = get.call_args.kwargs["params"]
        self.assertNotIn("models", params)
        self.assertEqual((params["start_date"], params["end_date"]), ("2017-01-01", "2025-12-31"))

    def test_models_and_range_are_passed(self):
        with patch.object(om.requests, "get", return_value=_response()) as get:
            om.fetch_district(-5.0, -80.0, start_date="2000-01-01", end_date="2016-12-31", models="era5")
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["models"], "era5")
        self.assertEqual((params["start_date"], params["end_date"]), ("2000-01-01", "2016-12-31"))

    def test_grid_cell_only_with_a_fixed_model(self):
        r = _response()
        r.json.return_value.update({"latitude": -5.0, "longitude": -80.25, "elevation": 30.0})
        with patch.object(om.requests, "get", return_value=r):
            default = om.fetch_district(-5.0, -80.0)
            fixed = om.fetch_district(-5.0, -80.0, models="era5")
        self.assertEqual(sorted(default.columns), sorted(["time", *om.DAILY_VARS]))
        self.assertEqual(fixed[["lat_celda", "lon_celda", "elevacion_celda"]].iloc[0].tolist(), [-5.0, -80.25, 30.0])

    def test_requested_daily_variables(self):
        with patch.object(om.requests, "get", return_value=_response(om.ERA5_LAND_DAILY_VARS)) as get:
            out = om.fetch_district(-5.0, -80.0, models="era5_land", daily_vars=om.ERA5_LAND_DAILY_VARS)
        self.assertEqual(get.call_args.kwargs["params"]["daily"], ",".join(om.ERA5_LAND_DAILY_VARS))
        self.assertEqual(sorted(out.columns), sorted(["time", *om.ERA5_LAND_DAILY_VARS, *om.GRID_COLUMNS]))
        with patch.object(om.requests, "get", return_value=_response()):
            with self.assertRaises(RuntimeError):  # more columns than requested
                om.fetch_district(-5.0, -80.0, models="era5_land", daily_vars=om.ERA5_LAND_DAILY_VARS)

    def test_fixed_model_rejects_renamed_columns(self):
        renamed = [f"{c}_era5" for c in om.DAILY_VARS]
        with patch.object(om.requests, "get", return_value=_response(renamed)):
            with self.assertRaises(RuntimeError):
                om.fetch_district(-5.0, -80.0, models="era5")


class TestDownloadPendingBatch(unittest.TestCase):
    districts = pd.DataFrame({"id_distrito": [1, 2], "distrito": ["A", "B"], "lat": [-5.0, -5.1],
                              "lon": [-80.0, -80.1]})

    def test_other_range_cannot_use_the_default_cache(self):
        with self.assertRaises(ValueError):
            om.download_pending_batch(self.districts, start_date="2000-01-01", end_date="2016-12-31")
        with self.assertRaises(ValueError):
            om.download_pending_batch(self.districts, models="era5", cache_dir=CACHE_METEO)
        with self.assertRaises(ValueError):
            om.download_pending_batch(self.districts, daily_vars=om.ERA5_LAND_DAILY_VARS)

    def test_writes_to_its_own_cache_and_resumes(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(om.requests, "get", return_value=_response()) as get, \
                patch.object(om.time, "sleep"):
            cache = Path(tmp) / "cache"
            self.assertEqual(om.download_pending_batch(self.districts, models="era5", cache_dir=cache), 0)
            self.assertEqual(sorted(p.name for p in cache.iterdir()),
                             ["distrito_001.parquet", "distrito_002.parquet"])
            self.assertEqual(get.call_args.kwargs["params"]["models"], "era5")
            get.reset_mock()
            om.download_pending_batch(self.districts, models="era5", cache_dir=cache)
            get.assert_not_called()



def _limit(reason):
    r = MagicMock(status_code=429, headers={"content-type": "application/json"})
    r.json.return_value = {"reason": reason}
    return r


HOURLY = "Hourly API request limit exceeded. Please try again in the next hour."
DAILY = "Daily API request limit exceeded. Please try again tomorrow."


class TestDownloadAll(unittest.TestCase):
    districts = pd.DataFrame({"id_distrito": [1, 2, 3], "distrito": ["A", "B", "C"], "lat": [-5.0, -5.1, -5.2],
                              "lon": [-80.0, -80.1, -80.2]})

    def _run(self, responses, **kwargs):
        waits = []
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(om.requests, "get", side_effect=responses), patch.object(om.time, "sleep"):
            cache = Path(tmp) / "cache"
            left = om.download_all(self.districts, models="era5_land", cache_dir=cache, sleep=waits.append, **kwargs)
            files = sorted(p.name for p in cache.iterdir())
        return left, files, waits

    def test_limit_kind(self):
        self.assertEqual(om.APILimitError(HOURLY).kind, "hourly")
        self.assertEqual(om.APILimitError(DAILY).kind, "daily")

    def test_waits_after_the_hourly_limit_and_finishes(self):
        left, files, waits = self._run([_response(), _limit(HOURLY), _response(), _limit(HOURLY), _response()])
        self.assertEqual(left, 0)
        self.assertEqual(len(files), 3)
        self.assertEqual(waits, [om.HOURLY_WAIT_SECONDS] * 2)

    def test_stops_at_the_daily_limit(self):
        left, files, waits = self._run([_response(), _limit(DAILY)])
        self.assertEqual((left, len(files), waits), (2, 1, []))

    def test_stops_after_the_maximum_number_of_waits(self):
        left, files, waits = self._run([_response(), _limit(HOURLY), _limit(HOURLY)], max_hourly_waits=1)
        self.assertEqual((left, len(files), len(waits)), (2, 1, 1))

    def test_the_batch_still_prints_and_returns_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(om.requests, "get", side_effect=[_response(), _limit(HOURLY)]), \
                patch.object(om.time, "sleep"):
            left = om.download_pending_batch(self.districts, models="era5", cache_dir=Path(tmp) / "c")
        self.assertEqual(left, 2)


class TestEra5LandEndDate(unittest.TestCase):
    def test_five_days_before_today(self):
        import datetime as dt

        from denguekay.data.ingestion.openmeteo import era5_land_end_date

        self.assertEqual(era5_land_end_date(dt.date(2026, 11, 9)), "2026-11-04")


if __name__ == "__main__":
    unittest.main()
