"""Tests of the weekly aggregation of only the available variables (ERA5-Land, study 06 1b')."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from denguekay.data.processing import weekly_aggregation as wa

DISTRICTS = pd.DataFrame({"id_distrito": [1, 2], "provincia": ["P", "P"], "distrito": ["A", "B"],
                          "lat": [-5.0, -5.1], "lon": [-80.0, -80.1]})


def _daily(start, end, ids=(1, 2), precipitation=np.nan):
    days = pd.date_range(start, end)
    return pd.DataFrame([{"id_distrito": i, "time": d, "temperature_2m_mean": 20.0 + i,
                          "relative_humidity_2m_mean": 70.0, "precipitation_sum": precipitation}
                         for i in ids for d in days])


class TestAggregateAvailable(unittest.TestCase):
    def test_missing_variable_stays_empty_not_zero(self):
        # 2017-01-01 is a Sunday: two full MMWR weeks
        weekly = wa.aggregate_available_to_weekly(_daily("2017-01-01", "2017-01-14"), DISTRICTS,
                                                  ["temperature_2m_mean", "relative_humidity_2m_mean",
                                                   "precipitation_sum"])
        self.assertEqual(len(weekly), 4)
        self.assertTrue(weekly.precip_total_mm.isna().all())
        self.assertTrue((weekly.hum_rel_media == 70.0).all())
        self.assertEqual(sorted(weekly.temp_media.unique()), [21.0, 22.0])

    def test_a_partial_week_with_some_data_is_summed(self):
        daily = _daily("2017-01-01", "2017-01-07", ids=(1,), precipitation=2.0)
        daily.loc[0, "precipitation_sum"] = np.nan
        weekly = wa.aggregate_available_to_weekly(daily, DISTRICTS, ["precipitation_sum"])
        self.assertEqual(weekly.precip_total_mm.iloc[0], 12.0)

    def test_same_weeks_and_calendar_as_the_full_aggregation(self):
        daily = _daily("2016-12-31", "2017-01-21", precipitation=1.0)
        for v in wa.DAILY_TO_WEEKLY_AGG:
            if v not in daily and v != "time":
                daily[v] = 1.0
        full = wa.aggregate_to_weekly(daily, DISTRICTS, include_id=True)
        ours = wa.aggregate_available_to_weekly(daily, DISTRICTS, ["relative_humidity_2m_mean", "precipitation_sum"])
        key = ["id_distrito", "semana_inicio", "anio", "semana"]
        pd.testing.assert_frame_equal(full[key + ["hum_rel_media", "precip_total_mm"]].reset_index(drop=True),
                                      ours[key + ["hum_rel_media", "precip_total_mm"]].reset_index(drop=True))
        self.assertEqual(ours.semana_inicio.min(), pd.Timestamp("2017-01-01"))  # the 1-day week is dropped

    def test_unknown_variable_is_rejected(self):
        with self.assertRaises(ValueError):
            wa.aggregate_available_to_weekly(_daily("2017-01-01", "2017-01-07"), DISTRICTS, ["dew_point_2m_mean"])


class TestLoadDailyFromCaches(unittest.TestCase):
    def _write(self, folder, daily):
        folder.mkdir()
        for i, g in daily.groupby("id_distrito"):
            g.assign(time=g.time.dt.strftime("%Y-%m-%d")).to_parquet(folder / f"distrito_{i:03d}.parquet", index=False)

    def test_joins_two_ranges_and_rejects_overlaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c = (Path(tmp) / n for n in ("a", "b", "c"))
            self._write(a, _daily("2016-12-25", "2016-12-31"))
            self._write(b, _daily("2017-01-01", "2017-01-07"))
            self._write(c, _daily("2016-12-31", "2017-01-03"))
            both = wa.load_daily_from_caches([a, b], expected_districts=2)
            self.assertEqual(len(both), 2 * 14)
            weekly = wa.aggregate_available_to_weekly(both, DISTRICTS, ["relative_humidity_2m_mean"])
            self.assertEqual(sorted(weekly.semana_inicio.unique()),
                             [pd.Timestamp("2016-12-25"), pd.Timestamp("2017-01-01")])
            with self.assertRaises(ValueError):
                wa.load_daily_from_caches([a, c], expected_districts=2)


if __name__ == "__main__":
    unittest.main()
