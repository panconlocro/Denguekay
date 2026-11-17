"""The Sala step of v0-v3 trims to the version cutoff and keeps notified captures apart; ERA5-Land is optional."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from denguekay.data.ingestion import gadm_districts
from denguekay.pipelines import v4_inputs, weekly_update
from denguekay.pipelines.versions import CUTOFFS, NOTIFIED_CUTOFF, V4_CUTOFF

CATALOG = pd.DataFrame({"ubigeo": ["200101"], "provincia_sala": ["PIURA"], "distrito_sala": ["PIURA"]})


class TestSalaStep(unittest.TestCase):
    def run_refresh(self, definition, weeks, cutoff):
        folders = []

        async def scrape(year, targets, folder=None, url=None, *, case_definition="confirmados"):
            folders.append(folder)
            return [{"anio": year}], []

        def normalize(records, controls, catalog):
            return pd.DataFrame({"ubigeo": "200101", "anio": 2026, "semana": weeks, "casos_Dengue": 1})

        with TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(weekly_update, "scrape_sala", scrape), \
                    patch.object(weekly_update, "normalize_sala_records", normalize), \
                    patch.object(weekly_update, "load_ubigeo_catalog", return_value=CATALOG), \
                    patch.object(weekly_update, "SILVER_SALA", root / "sala.csv"), \
                    patch.object(weekly_update, "BRONZE_SALA", root / "confirmados"), \
                    patch.object(weekly_update, "BRONZE_SALA_NOTIFIED", root / "notificados"):
                result = asyncio.run(weekly_update.refresh_sala_silver_async(
                    [2026], case_definition=definition, cutoff=cutoff))
                saved = pd.read_csv(root / "sala.csv")
        return result, saved, folders, root

    def test_weeks_after_the_cutoff_are_not_kept(self):
        result, saved, _, _ = self.run_refresh("notificados", [42, 43, 44, 45], NOTIFIED_CUTOFF)
        self.assertEqual(sorted(saved.semana), [42, 43])
        self.assertEqual(len(result), 2)

    def test_without_cutoff_everything_is_kept(self):
        _, saved, _, _ = self.run_refresh("notificados", [43, 44], None)
        self.assertEqual(sorted(saved.semana), [43, 44])

    def test_notified_captures_go_to_their_own_folder(self):
        _, _, folders, root = self.run_refresh("notificados", [1], None)
        self.assertEqual(folders[0].parent, root / "notificados")
        _, _, folders, root = self.run_refresh("confirmados", [1], None)
        self.assertEqual(folders[0].parent, root / "confirmados")

    def test_cutoffs_of_the_versions(self):
        self.assertEqual(set(CUTOFFS), {"v0", "v1", "v2", "v3", "v4"})
        self.assertIs(CUTOFFS["v4"], V4_CUTOFF)
        self.assertEqual(CUTOFFS["v3"].sala_last_week, V4_CUTOFF.sala_last_week)
        self.assertIsNone(CUTOFFS["v3"].labels)


class TestWeatherSwitch(unittest.TestCase):
    def test_without_era5_land_only_the_panel_cache_is_downloaded(self):
        with patch.object(v4_inputs.openmeteo, "download_all", return_value=[]) as download:
            result = v4_inputs.download_weather(era5_land=False)
        self.assertEqual(download.call_count, 1)
        self.assertEqual(result["caches"], 1)

    def test_an_incomplete_panel_cache_stops_the_step(self):
        with patch.object(v4_inputs.openmeteo, "download_all", return_value=[1, 2]):
            with self.assertRaises(RuntimeError):
                v4_inputs.download_weather(era5_land=False)


class TestGadmComparison(unittest.TestCase):
    def test_keeps_the_rebuilt_catalogue_in_bronze_and_never_overwrites_the_reference(self):
        reference = pd.DataFrame({"distrito": ["A", "B"], "lat": [-5.1, -5.2], "lon": [-80.1, -80.2]})
        rebuilt = reference.assign(lat=[-5.1, -5.2 + 1e-9])
        with TemporaryDirectory() as temp:
            path, output = Path(temp) / "reference.csv", Path(temp) / "bronze" / "geografia" / "gadm.csv"
            reference.to_csv(path, index=False)
            before = path.read_bytes()
            result = gadm_districts.compare_with_reference(rebuilt, path, output)
            self.assertEqual(path.read_bytes(), before)
            self.assertTrue(output.is_file())
        self.assertTrue(result["misma_forma"])
        self.assertTrue(result["otras_columnas_iguales"])
        self.assertAlmostEqual(result["diferencia_max_lat_lon"]["lat"], 1e-9, places=12)
        self.assertEqual(result["diferencia_max_lat_lon"]["lon"], 0.0)

    def test_reports_a_different_shape(self):
        reference = pd.DataFrame({"distrito": ["A"], "lat": [-5.1], "lon": [-80.1]})
        rebuilt = pd.concat([reference, reference], ignore_index=True)
        with TemporaryDirectory() as temp:
            path = Path(temp) / "reference.csv"
            reference.to_csv(path, index=False)
            result = gadm_districts.compare_with_reference(rebuilt, path, Path(temp) / "gadm.csv")
        self.assertFalse(result["misma_forma"])


if __name__ == "__main__":
    unittest.main()
