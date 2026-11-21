"""Real extraction date, in UTC, of every capture of the weekly update, and its archive in the emission (HU0002-1, §11)."""

from datetime import date, datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from denguekay.data.ingestion import enso
from denguekay.pipelines import v4_inputs, v4_weekly

NOW = datetime(2026, 11, 21, 3, 30, tzinfo=timezone.utc)   # still the 20th in Lima (UTC-5), already the 21st in UTC


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


class TestUtcDates(unittest.TestCase):
    def test_a_capture_is_named_by_the_utc_day_never_by_the_local_one(self):
        with patch.object(v4_inputs, "datetime", FixedClock):
            self.assertEqual(v4_inputs.utc_today(), date(2026, 11, 21))

    def test_the_noaa_download_is_named_by_the_utc_day(self):
        class Response:
            text = enso.HEADER + "\n2026  10  1.0  0.1  1.0  0.1  1.0  0.1  1.0  0.1\n"

            def raise_for_status(self):
                pass

        class Clock:
            datetime = FixedClock
            timezone = timezone
            date = date

        with TemporaryDirectory() as folder, patch.object(enso, "dt", Clock), \
                patch.object(enso.requests, "get", return_value=Response()):
            self.assertEqual(enso.download_sstoi(Path(folder)).name, "sstoi_20261121.indices")


class TestEra5Capture(unittest.TestCase):
    def test_the_sidecar_records_the_utc_instant_once_and_names_the_last_day_of_data(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory) / "2026-11-15"
            first = v4_inputs.record_era5_capture(folder, "2026-11-15")
            self.assertEqual(first.name, "2026-11-15.captura.json")   # beside the folder, not inside it
            record = json.loads(first.read_text(encoding="utf-8"))
            self.assertTrue(record["extraido_utc"].endswith("+00:00"))
            self.assertEqual(record["ultimo_dia_de_datos"], "2026-11-15")
            v4_inputs.record_era5_capture(folder, "2026-11-15")   # a resumed run does not move the date
            self.assertEqual(json.loads(first.read_text(encoding="utf-8")), record)

    def test_the_download_writes_the_sidecar_only_for_the_recent_folder_once_it_is_complete(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            pd.DataFrame({"id_distrito": [1]}).to_csv(root / "coords.csv", index=False)
            recent = root / "recent"
            common = dict(DISTRICT_COORDS=root / "coords.csv", CACHE_METEO_ERA5_LAND_RECENT=recent)
            with patch.multiple(v4_inputs, **common), patch.object(v4_inputs, "_weather_caches", return_value=[]), \
                    patch.object(v4_inputs.openmeteo, "era5_land_end_date", return_value="2026-11-15"):
                with patch.object(v4_inputs.openmeteo, "download_all", return_value=1):   # one district pending
                    with self.assertRaises(RuntimeError):
                        v4_inputs.download_era5_land()
                self.assertFalse((recent / "2026-11-15.captura.json").exists())
                with patch.object(v4_inputs.openmeteo, "download_all", return_value=0):
                    v4_inputs.download_era5_land()
            self.assertTrue((recent / "2026-11-15.captura.json").is_file())


class TestStepCaptures(unittest.TestCase):
    def build(self, root, *, era5_sidecar=True):
        sala, era5, chirps, noaa = root / "sala", root / "era5", root / "chirps", root / "enso"
        for path in (sala / "2025_20261120T071341806116Z", sala / "2026_20261117T164356748726Z",
                     sala / "2026_20261120T071422423111Z", era5 / "2026-11-12", era5 / "2026-11-15"):
            path.mkdir(parents=True)
        chirps.mkdir()
        (chirps / "20261117T165346038218Z.zip").write_bytes(b"x")
        (chirps / "20261120T072054289060Z.zip").write_bytes(b"x")
        noaa.mkdir()
        (noaa / "sstoi_20261117.indices").write_text("x")
        (noaa / "sstoi_20261120.indices").write_text("x")
        if era5_sidecar:
            v4_inputs.record_era5_capture(era5 / "2026-11-15", "2026-11-15")
        return patch.multiple(v4_weekly, BRONZE_SALA=sala, CACHE_METEO_ERA5_LAND_RECENT=era5,
                              V4_CHIRPS_SNAPSHOTS=chirps, BRONZE_ENSO=noaa)

    def test_each_source_reports_its_newest_capture_with_its_utc_extraction_time(self):
        with TemporaryDirectory() as directory, self.build(Path(directory)), \
                patch.object(v4_weekly, "datetime", FixedClock):
            captures = v4_weekly.step_captures()
        self.assertEqual(captures["sala"]["2026"], {"archivo": "2026_20261120T071422423111Z",
                                                    "extraido_utc": "2026-11-20T07:14:22.423111+00:00",
                                                    "precision": "instante"})
        self.assertEqual(captures["sala"]["2025"]["extraido_utc"], "2026-11-20T07:13:41.806116+00:00")
        self.assertEqual(captures["chirps"], {"archivo": "20261120T072054289060Z.zip",
                                              "extraido_utc": "2026-11-20T07:20:54.289060+00:00",
                                              "precision": "instante"})
        self.assertEqual(captures["enso"], {"archivo": "sstoi_20261120.indices", "extraido_utc": "2026-11-20",
                                            "precision": "dia"})
        era5 = captures["era5_land_reciente"]
        self.assertEqual((era5["archivo"], era5["precision"]), ("2026-11-15", "instante"))
        self.assertTrue(era5["extraido_utc"].endswith("+00:00"))   # the instant of the sidecar, not the folder's day

    def test_an_era5_folder_without_sidecar_says_that_nothing_recorded_its_extraction(self):
        with TemporaryDirectory() as directory, self.build(Path(directory), era5_sidecar=False):
            era5 = v4_weekly.step_captures()["era5_land_reciente"]
        self.assertEqual(era5, {"archivo": "2026-11-15", "extraido_utc": None, "precision": "sin_registro"})

    def test_the_stamp_of_a_name_becomes_a_utc_instant_and_anything_else_is_none(self):
        self.assertEqual(v4_weekly.utc_from_stamp("20261120T071341806116Z"), "2026-11-20T07:13:41.806116+00:00")
        self.assertIsNone(v4_weekly.utc_from_stamp("2026-11-20"))


if __name__ == "__main__":
    unittest.main()
