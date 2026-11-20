"""The V4 silver reads the coordinates the way the frozen Release files were written."""

import asyncio
from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd

from denguekay.data.ingestion.minsa_sala_scraper import SalaYearWithoutWeeks
from denguekay.pipelines import v4_inputs
from denguekay.pipelines.versions import V4_CUTOFF


class TestDistrictCoords(unittest.TestCase):
    def test_arenal_keeps_the_latitude_of_the_release(self):
        text = "provincia,distrito,lat,lon,distrito_key,id_distrito\nPaita,Arenal,-4.8996990381835985,-81.02889919655017,ARENAL,30\n"
        with TemporaryDirectory() as temp:
            path = Path(temp) / "coords.csv"
            path.write_text(text, encoding="utf-8")
            with patch.object(v4_inputs, "DISTRICT_COORDS", path), \
                    patch.object(v4_inputs.pd, "read_csv", wraps=pd.read_csv) as read:
                coords = v4_inputs.read_district_coords()
            read.assert_called_once_with(path)
            default = pd.read_csv(path)
        # The full frame checks the parser contract; a hard-coded float repr is not portable across pandas builds.
        pd.testing.assert_frame_equal(coords, default, check_exact=True)


class TestEra5LandSplit(unittest.TestCase):
    def test_download_weather_delegates_the_era5_land_half(self):
        with patch.object(v4_inputs.openmeteo, "download_all", return_value=[]), \
                patch.object(v4_inputs, "read_district_coords"), \
                patch.object(v4_inputs.pd, "read_csv", return_value=pd.DataFrame({"a": [1, 2]})), \
                patch.object(v4_inputs, "download_era5_land", return_value={"distritos": 2, "caches": 4}) as half:
            result = v4_inputs.download_weather()
        half.assert_called_once_with()
        self.assertEqual(result, {"distritos": 2, "caches": 4})

    def test_download_era5_land_passes_the_wait_limit_only_when_given(self):
        with patch.object(v4_inputs.openmeteo, "download_all", return_value=[]) as download, \
                patch.object(v4_inputs.pd, "read_csv", return_value=pd.DataFrame({"a": [1]})), \
                patch.object(v4_inputs.openmeteo, "era5_land_end_date", return_value="2026-10-01"):
            result = v4_inputs.download_era5_land()
            self.assertEqual(result["caches"], 3)
            self.assertTrue(all("max_hourly_waits" not in call.kwargs for call in download.call_args_list))
            download.reset_mock()
            v4_inputs.download_era5_land(max_hourly_waits=2)
            self.assertTrue(all(call.kwargs["max_hourly_waits"] == 2 for call in download.call_args_list))

    def test_download_era5_land_stops_on_an_incomplete_cache(self):
        with patch.object(v4_inputs.openmeteo, "download_all", return_value=[1]), \
                patch.object(v4_inputs.pd, "read_csv", return_value=pd.DataFrame({"a": [1]})), \
                patch.object(v4_inputs.openmeteo, "era5_land_end_date", return_value="2026-10-01"):
            with self.assertRaises(RuntimeError):
                v4_inputs.download_era5_land()

    @staticmethod
    def weekly():
        starts = pd.date_range("2026-10-04", periods=6, freq="W-SUN")
        return pd.DataFrame({"id_distrito": 1, "semana_inicio": starts, "temp_media": 25.0})

    def test_era5_land_silver_without_cutoff_writes_only_the_given_output(self):
        with TemporaryDirectory() as temp:
            release, output = Path(temp) / "release.csv", Path(temp) / "operativo" / "era5.csv"
            with patch.object(v4_inputs, "V4_ERA5_LAND", release), \
                    patch.object(v4_inputs, "read_district_coords"), \
                    patch.object(v4_inputs, "_era5_land_weekly", return_value=self.weekly()):
                free = v4_inputs.era5_land_silver(cutoff=None, output=output)
                self.assertFalse(release.exists())
                self.assertEqual(free["filas"], 6)
                clipped = v4_inputs.era5_land_silver()
                self.assertTrue(release.exists())
                self.assertEqual(clipped["filas"], 4)   # V4_CUTOFF keeps up to the week of 2026-10-25
            self.assertEqual(len(pd.read_csv(output)), 6)

    def test_weather_silver_keeps_calling_both_halves_with_the_same_files(self):
        with TemporaryDirectory() as temp:
            panel, era = Path(temp) / "panel.csv", Path(temp) / "era5.csv"
            with patch.object(v4_inputs, "V4_PANEL_WEATHER", panel), patch.object(v4_inputs, "V4_ERA5_LAND", era), \
                    patch.object(v4_inputs, "read_district_coords", return_value=pd.DataFrame({"a": [1]})), \
                    patch.object(v4_inputs, "load_daily_from_caches"), \
                    patch.object(v4_inputs, "aggregate_to_weekly", return_value=pd.DataFrame({"x": [1]})), \
                    patch.object(v4_inputs, "clean_names_for_join", side_effect=lambda frame: frame), \
                    patch.object(v4_inputs, "_era5_land_weekly", return_value=self.weekly()):
                result = v4_inputs.weather_silver()
                self.assertEqual([item["archivo"] for item in result], ["panel.csv", "era5.csv"])
                self.assertEqual(len(pd.read_csv(era)), 4)
                self.assertEqual(len(v4_inputs.weather_silver(era5_land=False)), 1)


class TestClimateOutputs(unittest.TestCase):
    def test_climate_silver_writes_without_cutoff_to_the_given_outputs(self):
        months = pd.DataFrame({"anio": [2026, 2026], "mes": [10, 11], "nino12_anom": [0.1, 0.2],
                               "fecha_disponible": ["2026-11-10", "2026-12-10"]})
        days = pd.DataFrame({"fecha": ["2026-11-01"]})
        weekly = pd.DataFrame({"ubigeo": "200101", "semana_inicio": ["2026-10-25", "2026-11-01"],
                               "precip_total_mm": [1.0, 2.0]})
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "enso").mkdir()
            (root / "enso" / "sstoi_20261101.indices").write_text("x", encoding="utf-8")
            release_enso, release_chirps = root / "release_enso.csv", root / "release_chirps.csv"
            with patch.object(v4_inputs, "BRONZE_ENSO", root / "enso"), \
                    patch.object(v4_inputs, "BRONZE_CHIRPS_EE_FINAL", root / "ee"), \
                    patch.object(v4_inputs, "V4_ENSO", release_enso), patch.object(v4_inputs, "V4_CHIRPS", release_chirps), \
                    patch.object(v4_inputs, "nino12_monthly", return_value=months), \
                    patch.object(v4_inputs.chirps_ee, "load_districts"), \
                    patch.object(v4_inputs.rain, "daily_from_windows", return_value=days), \
                    patch.object(v4_inputs.rain, "combine_daily_by_week", return_value=days), \
                    patch.object(v4_inputs.rain, "weekly_by_version", return_value=(weekly, pd.DataFrame())):
                result = v4_inputs.climate_silver(offline=True, cutoff=None, enso_output=root / "o" / "enso.csv",
                                                  chirps_output=root / "o" / "chirps.csv")
                self.assertEqual([item["filas"] for item in result["series"]], [2, 2])
                self.assertFalse(release_enso.exists() or release_chirps.exists())
                clipped = v4_inputs.climate_silver(offline=True)
                self.assertEqual([item["filas"] for item in clipped["series"]], [1, 1])   # V4_CUTOFF drops 2026-11
                self.assertEqual(V4_CUTOFF.enso_last_month, (2026, 10))


CATALOG_TEXT = "provincia,distrito,ubigeo\nPiura,Piura,200101\n"


class FixedDate(date):
    """``date`` whose ``today`` is a fixed day, for the new-year cases."""
    day = date(2027, 6, 1)

    @classmethod
    def today(cls):
        return cls.day


class TestSalaOperational(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "catalogo.csv").write_text(CATALOG_TEXT, encoding="utf-8")
        self.calls = []
        patches = patch.multiple(v4_inputs, BRONZE_SALA=self.root / "bronze", V4_SALA=self.root / "release.csv",
                                 UBIGEO_CATALOG=self.root / "catalogo.csv", scrape_sala=self.fake_scrape)
        patches.start()
        self.addCleanup(patches.stop)

    async def fake_scrape(self, year, targets, folder):
        self.calls.append(year)
        folder.mkdir(parents=True, exist_ok=True)
        if year in getattr(self, "empty_years", ()):
            raise RuntimeError(f"Sala extraction failed for {year}") from SalaYearWithoutWeeks("sin semanas")
        self.write_capture(folder, year, 5)

    @staticmethod
    def write_capture(folder, year, cases):
        folder.mkdir(parents=True, exist_ok=True)
        week = f"{year}-01"
        chart = {"title": [{"text": "Tendencia semanal de casos segun tipo de diagnostico"}],
                 "xAxis": [{"data": [week]}],
                 "series": [{"name": "CONFIRMADO", "data": [{"value": [week, cases]}]}]}
        for level in ("departamento", "provincia", "distrito"):
            record = {"anio": year, "tipo_dx": "C", "nivel": level, "provincia": "PIURA", "distrito": "PIURA",
                      "chart": {"x": {"opts": chart}}}
            (folder / f"{level}.json").write_text(json.dumps(record), encoding="utf-8")

    def run_sala(self, **kwargs):
        return asyncio.run(v4_inputs.sala_silver(**kwargs))

    def test_default_scrapes_every_year_and_keeps_the_cutoff(self):
        self.run_sala(year=2026)
        self.assertEqual(self.calls, [2025, 2026])
        self.assertTrue((self.root / "release.csv").exists())

    def test_without_cutoff_it_writes_the_given_output_and_not_the_release_file(self):
        output = self.root / "operativo" / "sala.csv"
        report = self.run_sala(year=2026, cutoff=None, output=output)
        self.assertEqual(report["filas"], 2)
        self.assertEqual(sorted(pd.read_csv(output).anio), [2025, 2026])
        self.assertFalse((self.root / "release.csv").exists())

    def test_refresh_years_scrape_only_those_and_replay_the_rest(self):
        self.write_capture(self.root / "bronze" / "2025_20260101T000000000000Z", 2025, 7)
        self.run_sala(year=2026, cutoff=None, output=self.root / "o.csv", refresh_years={2026})
        self.assertEqual(self.calls, [2026])
        saved = pd.read_csv(self.root / "o.csv")
        self.assertEqual(dict(zip(saved.anio, saved.casos_Dengue)), {2025: 7, 2026: 5})

    def test_a_year_without_capture_falls_back_to_a_live_scrape(self):
        self.run_sala(year=2026, cutoff=None, output=self.root / "o.csv", refresh_years={2026})
        self.assertEqual(self.calls, [2025, 2026])

    def test_a_capture_that_does_not_replay_falls_back_to_a_live_scrape(self):
        self.write_capture(self.root / "bronze" / "2025_20260101T000000000000Z", 2024, 7)   # another year
        self.run_sala(year=2026, cutoff=None, output=self.root / "o.csv", refresh_years={2026})
        self.assertEqual(self.calls, [2025, 2026])

    def test_offline_replays_everything_and_never_scrapes(self):
        self.write_capture(self.root / "bronze" / "2025_20260101T000000000000Z", 2025, 7)
        self.write_capture(self.root / "bronze" / "2026_20260101T000000000000Z", 2026, 8)
        self.run_sala(year=2026, offline=True, refresh_years={2026}, cutoff=None, output=self.root / "o.csv")
        self.assertEqual(self.calls, [])
        with self.assertRaises(FileNotFoundError):
            self.run_sala(year=2027, offline=True, cutoff=None, output=self.root / "o.csv")

    def test_a_new_year_without_weeks_is_skipped_during_january(self):
        self.empty_years = {2027}
        FixedDate.day = date(2027, 1, 5)
        with patch.object(v4_inputs, "date", FixedDate):
            self.run_sala(cutoff=None, output=self.root / "o.csv", refresh_years={2026, 2027})
        self.assertEqual(sorted(set(pd.read_csv(self.root / "o.csv").anio)), [2025, 2026])
        self.assertEqual(sorted(path.name[:4] for path in (self.root / "bronze").iterdir()), ["2025", "2026"])

    def test_the_skip_does_not_apply_later_in_the_year_or_to_other_years(self):
        self.empty_years = {2027}
        FixedDate.day = date(2027, 6, 1)
        with patch.object(v4_inputs, "date", FixedDate), self.assertRaises(RuntimeError):
            self.run_sala(cutoff=None, output=self.root / "o.csv")
        self.empty_years = {2026}
        FixedDate.day = date(2027, 1, 5)
        with patch.object(v4_inputs, "date", FixedDate), self.assertRaises(RuntimeError):
            self.run_sala(cutoff=None, output=self.root / "o.csv")
        self.empty_years = set()
        self.write_capture(self.root / "unrelated", 2025, 1)

    def test_a_different_scrape_error_is_never_skipped(self):
        async def broken(year, targets, folder):
            raise RuntimeError("Sala extraction failed: timeout")

        FixedDate.day = date(2027, 1, 5)
        with patch.object(v4_inputs, "date", FixedDate), patch.object(v4_inputs, "scrape_sala", broken):
            with self.assertRaises(RuntimeError):
                self.run_sala(cutoff=None, output=self.root / "o.csv")

    def test_offline_new_year_without_capture_is_skipped_only_during_january(self):
        self.write_capture(self.root / "bronze" / "2025_20260101T000000000000Z", 2025, 7)
        self.write_capture(self.root / "bronze" / "2026_20260101T000000000000Z", 2026, 8)
        FixedDate.day = date(2027, 1, 5)
        with patch.object(v4_inputs, "date", FixedDate):
            self.run_sala(offline=True, cutoff=None, output=self.root / "o.csv")
        self.assertEqual(sorted(set(pd.read_csv(self.root / "o.csv").anio)), [2025, 2026])
        FixedDate.day = date(2027, 6, 1)
        with patch.object(v4_inputs, "date", FixedDate), self.assertRaises(FileNotFoundError):
            self.run_sala(offline=True, cutoff=None, output=self.root / "o.csv")


class TestEnsureOperationalRelease(unittest.TestCase):
    def run_ensure(self, present):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            names = {"V4_INTEGRATED": "data/silver/confirmados/panel.csv", "V4_HISTORY": "data/silver/confirmados/hist.csv",
                     "V4_GEOGRAPHY": "geo/geografia.csv", "V4_FROZEN": "models/v4"}
            paths = {name: root / relative for name, relative in names.items()}
            coverage = root / "data/silver/confirmados/panel.coverage.csv"
            for name in present:
                target = coverage if name == "coverage" else paths[name] / "paquete.json" if name == "V4_FROZEN" else paths[name]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("x", encoding="utf-8")
            with patch.multiple(v4_inputs, ROOT=root, **paths), \
                    patch.object(v4_inputs, "coverage_path", return_value=coverage), \
                    patch.object(v4_inputs.release_bundles, "manifest_path", return_value="manifiesto"), \
                    patch.object(v4_inputs.release_bundles, "fetch", return_value={}) as fetch:
                v4_inputs.ensure_operational_release()
        return fetch.call_args_list

    def test_everything_present_downloads_nothing(self):
        self.assertEqual(self.run_ensure({"V4_INTEGRATED", "coverage", "V4_HISTORY", "V4_GEOGRAPHY", "V4_FROZEN"}), [])

    def test_only_the_missing_files_are_requested_and_nothing_is_overwritten(self):
        calls = self.run_ensure({"V4_INTEGRATED", "V4_HISTORY", "V4_GEOGRAPHY"})
        self.assertEqual([(call.kwargs["only"], call.kwargs["prefixes"]) for call in calls], [
            (["datos_v4.zip"], ("data/silver/confirmados/panel.coverage.csv",)),
            (["modelo_v4.zip"], ("models/v4",)),
        ])
        for call in calls:
            self.assertNotIn("overwrite", call.kwargs)
            self.assertFalse(any(prefix.startswith("data/gold") for prefix in call.kwargs["prefixes"]))

    def test_everything_missing_asks_for_the_data_files_and_the_package(self):
        calls = self.run_ensure(set())
        self.assertEqual(calls[0].kwargs["only"], ["datos_v4.zip"])
        self.assertEqual(set(calls[0].kwargs["prefixes"]), {
            "data/silver/confirmados/panel.csv", "data/silver/confirmados/panel.coverage.csv",
            "data/silver/confirmados/hist.csv", "geo/geografia.csv"})
        self.assertEqual(calls[1].kwargs["only"], ["modelo_v4.zip"])


if __name__ == "__main__":
    unittest.main()
