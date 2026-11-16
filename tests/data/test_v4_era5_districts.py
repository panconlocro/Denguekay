"""Confirm weather district lookup uses catalogue IDs and checks the names."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from denguekay.data.processing.district_locations import district_locations, read_v4_era5


class TestV4Era5Districts(unittest.TestCase):
    def test_ulp_difference_in_coordinates_does_not_lose_districts(self):
        points = district_locations().query("distrito in ['ARENAL', 'MIGUELCHECA']")
        self.assertEqual(len(points), 2)
        weather = points.drop(columns="ubigeo").assign(
            lat=points.lat.round(14), semana_inicio="2026-09-27", temp_media=25,
        )
        with TemporaryDirectory() as folder:
            path = Path(folder) / "era5.csv"
            weather.to_csv(path, index=False)
            data = read_v4_era5(path)
            self.assertEqual(list(data.ubigeo), list(points.ubigeo))
            self.assertTrue(data.fecha_disponible.eq(pd.Timestamp("2026-10-10")).all())

            weather["id_distrito"] = weather.id_distrito.to_numpy()[::-1]
            weather.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "district IDs or names"):
                read_v4_era5(path)
