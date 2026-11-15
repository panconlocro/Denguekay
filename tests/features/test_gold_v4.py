"""Verify that B3's training features honor the archived availability rules."""

import unittest

import pandas as pd

from denguekay.features.b3 import NINO, WEATHER
from denguekay.features.gold_v4 import climate_table


class TestV4ClimateTable(unittest.TestCase):
    def test_uses_only_the_five_eligible_weeks_and_three_published_months(self):
        dates = pd.date_range("2026-08-30", periods=8, freq="W-SUN")
        weather = pd.DataFrame({
            "ubigeo": "010101", "semana_inicio": dates, "temp_media": range(8), "hum_rel_media": 50,
            "precip_total_mm": 6, "fecha_disponible": dates + pd.Timedelta(days=13),
        })
        enso = pd.DataFrame({
            "anio": 2026, "mes": [6, 7, 8, 9], "nino12_anom": [0, -1, 1, 85],
            "fecha_disponible": pd.to_datetime(["2026-07-10", "2026-08-10", "2026-09-10", "2026-10-18"]),
        })
        origins = pd.DataFrame({"ubigeo": ["010101"], "origen_cierre": pd.to_datetime(["2026-10-17"])})
        result = climate_table(weather, weather, enso, origins)
        self.assertEqual(result.at[0, NINO], 0)
        self.assertEqual(result.at[0, WEATHER["temp_media"][1]], 2)
        weather.loc[5:, "temp_media"] = 99
        pd.testing.assert_frame_equal(result, climate_table(weather, weather, enso, origins))
        weather.loc[4, "fecha_disponible"] = pd.Timestamp("2026-10-18")
        result = climate_table(weather, weather, enso, origins)
        self.assertTrue(pd.isna(result.at[0, WEATHER["temp_media"][1]]))
