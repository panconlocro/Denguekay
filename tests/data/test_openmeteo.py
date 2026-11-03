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


if __name__ == "__main__":
    unittest.main()
