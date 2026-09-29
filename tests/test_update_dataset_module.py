"""Focused tests for selective source execution and snapshot integrity."""

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from src.ingestion.scrape_minsa_dengue import observed_weekly_points
from src.processing.epi_sala import normalize_sala_records
from src.processing.socio_interpolacion import SOCIO_COLUMNS, generar_socio_para_claves
from src.update_dataset_module import run_weather, update_dataset
from src.validation.expectations_integrado import WEATHER_COLUMNS, coverage_path, prepare_dataset


CODE = "200502"


def model_row(week: int) -> dict:
    row = {
        "provincia": "Paita", "distrito": "Amotape", "lat": -4.83, "lon": -81.0,
        "ubigeo": CODE, "anio": 2025, "semana": week,
        "semana_inicio": (date(2024, 12, 29) + timedelta(weeks=week - 1)).isoformat(),
        "casos_Dengue": 0, "poblacion": 1000,
    }
    row.update({column: 1.0 for column in WEATHER_COLUMNS})
    row.update({column: 0.5 for column in SOCIO_COLUMNS if column != "poblacion"})
    return row


def provider_for(component: str, calls: list[str]):
    def provider(_frame, keys):
        calls.append(component)
        rows = []
        for code, year, week in sorted(keys):
            row = {"ubigeo": code, "anio": year, "semana": week}
            if component == "epidemiological":
                row["casos_Dengue"] = 4
            elif component == "weather":
                row.update({column: 2.0 for column in WEATHER_COLUMNS})
            else:
                row.update({column: 0.4 for column in SOCIO_COLUMNS})
                row["poblacion"] = 1100
            rows.append(row)
        return pd.DataFrame(rows)
    return provider


class UpdateDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "model.csv"

    def write(self, rows):
        pd.DataFrame(rows).to_csv(self.path, index=False)

    def providers(self, calls):
        return {name: provider_for(name, calls) for name in ("epidemiological", "weather", "demographic")}

    def test_complete_dataset_skips_all_sources_and_second_run_is_stable(self):
        self.write([model_row(1), model_row(2)])
        calls = []
        update_dataset(self.path, self.path, providers=self.providers(calls))
        first = self.path.read_bytes()
        update_dataset(self.path, self.path, providers=self.providers(calls))
        self.assertEqual(calls, [])
        self.assertEqual(first, self.path.read_bytes())
        self.assertEqual(len(pd.read_csv(self.path)), 2)
        self.assertTrue(coverage_path(self.path).exists())

    def test_missing_only_cases_runs_only_sala(self):
        rows = [model_row(1), model_row(2)]
        rows[1]["casos_Dengue"] = None
        self.write(rows)
        calls = []
        update_dataset(self.path, self.path, providers=self.providers(calls))
        self.assertEqual(calls, ["epidemiological"])
        self.assertEqual(pd.read_csv(self.path)["casos_Dengue"].tolist(), [0, 4])

    def test_missing_only_weather_runs_only_openmeteo(self):
        rows = [model_row(1), model_row(2)]
        rows[1]["temp_media"] = None
        self.write(rows)
        calls = []
        update_dataset(self.path, self.path, providers=self.providers(calls))
        self.assertEqual(calls, ["weather"])
        result = pd.read_csv(self.path)
        self.assertEqual(result.loc[1, "temp_media"], 2.0)
        self.assertEqual(result.loc[1, "temp_max"], 1.0)

    def test_missing_only_demographics_runs_only_interpolation(self):
        rows = [model_row(1), model_row(2)]
        rows[1]["fraccion_rural"] = None
        self.write(rows)
        calls = []
        update_dataset(self.path, self.path, providers=self.providers(calls))
        self.assertEqual(calls, ["demographic"])
        result = pd.read_csv(self.path)
        self.assertEqual(result.loc[1, "fraccion_rural"], 0.4)
        self.assertEqual(result.loc[1, "poblacion"], 1000)

    def test_multiple_groups_and_absent_column_are_detected(self):
        rows = [model_row(1), model_row(2)]
        for row in rows:
            del row["temp_media"]
        rows[1]["casos_Dengue"] = None
        rows[1]["fraccion_rural"] = None
        self.write(rows)
        calls = []
        update_dataset(self.path, self.path, providers=self.providers(calls))
        self.assertEqual(calls, ["epidemiological", "weather", "demographic"])
        self.assertEqual(len(pd.read_csv(self.path)), 2)

    def test_new_zero_without_coverage_is_scraped(self):
        self.write([model_row(1)])
        update_dataset(self.path, self.path, providers=self.providers([]))
        self.write([model_row(1), model_row(2)])
        calls = []
        update_dataset(self.path, self.path, providers=self.providers(calls))
        self.assertEqual(calls, ["epidemiological"])
        self.assertEqual(pd.read_csv(self.path)["casos_Dengue"].tolist(), [0, 4])

    def test_new_2026_week_with_all_groups_missing_runs_all_three(self):
        existing = model_row(1)
        self.write([existing])
        update_dataset(self.path, self.path, providers=self.providers([]))
        new = model_row(1)
        new.update({"anio": 2026, "semana": 1, "semana_inicio": "2025-12-28", "casos_Dengue": None})
        for column in WEATHER_COLUMNS + SOCIO_COLUMNS:
            new[column] = None
        self.write([existing, new])
        calls = []
        update_dataset(self.path, self.path, providers=self.providers(calls))
        self.assertEqual(calls, ["epidemiological", "weather", "demographic"])
        result = pd.read_csv(self.path)
        self.assertEqual(len(result), 2)
        self.assertEqual(result.loc[1, "casos_Dengue"], 4)
        self.assertEqual(result.loc[1, "temp_media"], 2.0)
        self.assertEqual(result.loc[1, "poblacion"], 1100)

    def test_dry_run_and_source_failure_do_not_modify_files(self):
        self.write([model_row(1)])
        update_dataset(self.path, self.path, providers=self.providers([]))
        self.write([model_row(1), model_row(2)])
        before_model = self.path.read_bytes()
        before_state = coverage_path(self.path).read_bytes()
        calls = []
        missing = update_dataset(self.path, self.path, dry_run=True, providers=self.providers(calls))
        self.assertEqual(len(missing["epidemiological"]), 1)
        self.assertEqual(calls, [])
        failing = self.providers(calls)
        failing["epidemiological"] = Mock(side_effect=RuntimeError("Sala unavailable"))
        with self.assertRaisesRegex(RuntimeError, "Sala unavailable"):
            update_dataset(self.path, self.path, providers=failing)
        self.assertEqual(self.path.read_bytes(), before_model)
        self.assertEqual(coverage_path(self.path).read_bytes(), before_state)

    def test_duplicate_keys_are_rejected(self):
        self.write([model_row(1), model_row(1)])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            update_dataset(self.path, self.path, dry_run=True)

    def test_geographic_name_mismatch_is_rejected(self):
        row = model_row(1)
        row["distrito"] = "Arenal"
        self.write([row])
        with self.assertRaisesRegex(ValueError, "does not match UBIGEO"):
            update_dataset(self.path, self.path, dry_run=True)

    def test_forced_demographic_refresh_is_scoped_to_date_window(self):
        self.write([model_row(1), model_row(2)])
        update_dataset(self.path, self.path, providers=self.providers([]))
        calls = []
        update_dataset(
            self.path, self.path, force={"demographic"},
            start_date="2025-01-05", end_date="2025-01-05",
            providers=self.providers(calls),
        )
        self.assertEqual(calls, ["demographic"])
        result = pd.read_csv(self.path)
        self.assertEqual(result["poblacion"].tolist(), [1000, 1100])
        with self.assertRaisesRegex(ValueError, "Sunday"):
            update_dataset(
                self.path, self.path, dry_run=True, force={"demographic"},
                start_date="2025-01-06", end_date="2025-01-06",
            )

    def test_weather_uses_requested_week_only(self):
        frame = prepare_dataset(pd.DataFrame([model_row(1)]))
        days = pd.date_range("2024-12-29", periods=7).strftime("%Y-%m-%d").tolist()
        daily = pd.DataFrame({"time": days})
        for column in (
            "temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
            "precipitation_sum", "rain_sum", "relative_humidity_2m_mean",
            "wind_speed_10m_max", "shortwave_radiation_sum", "et0_fao_evapotranspiration",
        ):
            daily[column] = 1.0
        with patch("src.update_dataset_module.fetch_district", return_value=daily) as fetch:
            result = run_weather(frame, {(CODE, 2025, 1)})
        self.assertEqual(fetch.call_args.kwargs["start_date"], "2024-12-29")
        self.assertEqual(fetch.call_args.kwargs["end_date"], "2025-01-04")
        self.assertEqual(result.iloc[0]["precip_total_mm"], 7.0)

    def test_demographic_extrapolation_caps_fractions(self):
        silver = Path(self.temp.name) / "socio.csv"
        rows = []
        for year, population in ((2017, 1000), (2025, 1800)):
            row = {"ubigeo": CODE, "anio": year, "poblacion": population}
            row.update({column: 0.5 for column in SOCIO_COLUMNS if column != "poblacion"})
            row["fraccion_hogares_celular"] = 0.2 if year == 2017 else 1.0
            row["fraccion_sin_seguro"] = 0.8 if year == 2017 else 0.0
            rows.append(row)
        pd.DataFrame(rows).to_csv(silver, index=False)
        with self.assertLogs(level="INFO") as logs:
            result = generar_socio_para_claves({(CODE, 2026)}, silver, Path(self.temp.name) / "missing.xlsx")
        self.assertEqual(result.iloc[0]["poblacion"], 1900)
        self.assertEqual(result.iloc[0]["fraccion_hogares_celular"], 1.0)
        self.assertEqual(result.iloc[0]["fraccion_sin_seguro"], 0.0)
        self.assertTrue(any("district=200502 period=2026" in message for message in logs.output))

    def test_sala_week_53_is_kept_as_source_data(self):
        catalog = pd.DataFrame({
            "ubigeo": ["200502", "200503"],
            "provincia_sala": ["PAITA", "PAITA"],
            "distrito_sala": ["AMOTAPE", "ARENAL"],
        })
        points_52 = [[week, 0] for week in range(1, 53)]
        points_53 = points_52 + [[53, 1]]
        records = [
            {"provincia": "PAITA", "distrito": "AMOTAPE", "anio": 2025, "points": points_52},
            {"provincia": "PAITA", "distrito": "ARENAL", "anio": 2025, "points": points_53},
        ]
        controls = [
            {"nivel": "provincia", "provincia": "PAITA", "points": points_53},
            {"nivel": "departamento", "points": points_53},
        ]
        result = normalize_sala_records(records, controls, catalog)
        self.assertEqual(len(result), 106)
        self.assertEqual(result[result["semana"] == 53]["casos_Dengue"].sum(), 1)

    def test_sala_current_year_trailing_nulls_are_not_zero_cases(self):
        raw = [{"value": [1, 2]}, {"value": [2, 0]}, {"value": [3, None]}]
        self.assertEqual(observed_weekly_points(raw, 2026), [[1, 2], [2, 0]])
        with self.assertRaisesRegex(RuntimeError, "internal missing week"):
            observed_weekly_points(raw + [{"value": [4, 1]}], 2026)


if __name__ == "__main__":
    unittest.main()
