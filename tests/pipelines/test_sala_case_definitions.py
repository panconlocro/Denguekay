"""The Sala is read for confirmed cases (V4) or notified cases (v0-v3); the pipeline step runs inside a notebook."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import nbformat
from nbclient import NotebookClient
import pandas as pd

from denguekay.data.ingestion import minsa_sala_scraper as scraper
from denguekay.data.processing.epi_sala import upsert_sala_silver
from denguekay.pipelines import weekly_update


def chart_response(year, definition):
    week = f"{year}-01"
    if definition == "confirmados":
        chart = {"title": [{"text": "Tendencia semanal de casos segun tipo de diagnostico",
                            "subtext": "Dengue - Piura"}],
                 "xAxis": [{"data": [week]}],
                 "series": [{"name": "CONFIRMADO", "data": [{"value": [week, 5]}]},
                            {"name": "PROBABLE", "data": [{"value": [week, 99]}]}]}
    else:
        chart = {"title": [{"text": "Tendencia semanal"}],
                 "series": [{"name": str(year - 1), "data": [{"value": [1, 77]}]},
                            {"name": str(year), "data": [{"value": [1, 8]}, {"value": [2, None]}]}]}
    return {scraper.CHARTS[definition]: {"x": {"opts": chart}}}


class FakeClient(scraper.SalaClient):
    def __init__(self, definition):
        super().__init__(None, None, definition)
        self.sent = []

    async def call(self, data, method="update"):
        self.sent.append(data)
        return chart_response(2025, self.case_definition)


class TestScraperDefinitions(unittest.TestCase):
    def test_each_definition_reads_its_own_chart(self):
        for definition, expected in (("confirmados", 5), ("notificados", 8)):
            with self.subTest(definition):
                record = asyncio.run(FakeClient(definition).extract(2025))
                self.assertEqual(record["points"], [[1, expected]])
                self.assertEqual("tipo_dx" in record, definition == "confirmados")

    def test_notified_chart_must_be_weekly_and_have_the_year(self):
        weekly = chart_response(2025, "notificados")[scraper.CHARTS["notificados"]]["x"]["opts"]
        with self.assertRaises(RuntimeError):
            scraper.notified_weekly_points({**weekly, "title": [{"text": "Tendencia mensual"}]}, 2025)
        with self.assertRaises(RuntimeError):
            scraper.notified_weekly_points(weekly, 2030)

    def test_initial_inputs_follow_the_definition(self):
        confirmed = scraper.initial_inputs("", "confirmados")
        notified = scraper.initial_inputs("", "notificados")
        self.assertIn("ten-tog02a", confirmed)
        self.assertNotIn("ten-tog02a", notified)
        self.assertFalse(confirmed[".clientdata_output_ten-fig02a-echart_hidden"])
        self.assertFalse(notified[".clientdata_output_ten-fig02b-echart_hidden"])
        with self.assertRaises(ValueError):
            scraper.initial_inputs("", "probables")

    def test_unknown_definition_is_rejected_before_any_request(self):
        with self.assertRaises(ValueError):
            asyncio.run(scraper.scrape_sala(2025, set(), case_definition="probables"))


class TestUpsertDefinitions(unittest.TestCase):
    def test_notified_upsert_keeps_the_newest_row_and_has_no_diagnosis_column(self):
        old = pd.DataFrame({"ubigeo": ["200101"] * 2, "anio": [2025] * 2, "semana": [1, 2], "casos_Dengue": [1, 2]})
        new = pd.DataFrame({"ubigeo": ["200101"] * 2, "anio": [2025] * 2, "semana": [2, 3], "casos_Dengue": [9, 3]})
        with TemporaryDirectory() as temp:
            path = Path(temp) / "sala.csv"
            upsert_sala_silver(path, old, case_definition="notificados")
            upsert_sala_silver(path, new, case_definition="notificados")
            result = pd.read_csv(path, dtype={"ubigeo": "string"})
            self.assertEqual(result.casos_Dengue.tolist(), [1, 9, 3])
            with self.assertRaises(ValueError):
                upsert_sala_silver(path, new.assign(tipo_dx="C"), case_definition="notificados")

    def test_confirmed_upsert_still_requires_the_diagnosis_column(self):
        fresh = pd.DataFrame({"ubigeo": ["200101"], "anio": [2025], "semana": [1], "casos_Dengue": [1]})
        with TemporaryDirectory() as temp, self.assertRaises(ValueError):
            upsert_sala_silver(Path(temp) / "sala.csv", fresh)


CATALOG = pd.DataFrame({"ubigeo": ["200101"], "provincia_sala": ["PIURA"], "distrito_sala": ["PIURA"]})


async def fake_scrape(year, targets, folder=None, url=None, *, case_definition="confirmados"):
    record = {"anio": year, "points": [[1, 5]], "nivel": "distrito", "provincia": "PIURA", "distrito": "PIURA"}
    return [record], []


def fake_normalize(records, controls, catalog):
    return pd.DataFrame({"ubigeo": ["200101"], "anio": [records[0]["anio"]], "semana": [1], "casos_Dengue": [5]})


class TestStepInsideRunningLoop(unittest.TestCase):
    def patches(self, root):
        return (patch.object(weekly_update, "scrape_sala", fake_scrape),
                patch.object(weekly_update, "normalize_sala_records", fake_normalize),
                patch.object(weekly_update, "load_ubigeo_catalog", return_value=CATALOG),
                patch.object(weekly_update, "SILVER_SALA", root / "sala.csv"),
                patch.object(weekly_update, "BRONZE_SALA", root / "bronze"))

    def test_sync_entry_works_with_and_without_a_running_loop(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            a, b, c, d, e = self.patches(root)
            with a, b, c, d, e:
                self.assertEqual(len(weekly_update.refresh_sala_silver([2025], case_definition="notificados")), 1)

                async def inside_a_loop():
                    return weekly_update.refresh_sala_silver([2026], case_definition="notificados")

                self.assertEqual(len(asyncio.run(inside_a_loop())), 1)
                self.assertEqual(len(pd.read_csv(root / "sala.csv")), 2)

    def test_unknown_definition_is_rejected(self):
        with self.assertRaises(ValueError):
            weekly_update.refresh_sala_silver([2025], case_definition="probables")

    def test_runs_in_a_notebook_kernel_by_sync_call_and_by_await(self):
        setup = """
from pathlib import Path
import pandas as pd
from denguekay.pipelines import weekly_update as w
import sys
sys.path.insert(0, TESTS)
from pipelines.test_sala_case_definitions import fake_scrape, fake_normalize, CATALOG
w.scrape_sala, w.normalize_sala_records = fake_scrape, fake_normalize
w.load_ubigeo_catalog = lambda path: CATALOG
w.SILVER_SALA, w.BRONZE_SALA = Path("sala.csv"), Path("bronze")
"""
        calls = "\nsync = w.refresh_sala_silver([2025], case_definition='notificados')\n"
        awaited = "\nasync_result = await w.refresh_sala_silver_async([2026], case_definition='notificados')\n"
        tests_dir = str(Path(__file__).resolve().parents[1])
        notebook = nbformat.v4.new_notebook(cells=[
            nbformat.v4.new_code_cell(f"TESTS = {tests_dir!r}" + setup),
            nbformat.v4.new_code_cell(calls), nbformat.v4.new_code_cell(awaited)])
        with TemporaryDirectory() as temp:
            NotebookClient(notebook, timeout=120, resources={"metadata": {"path": temp}}).execute()
            self.assertEqual(len(pd.read_csv(Path(temp) / "sala.csv")), 2)


if __name__ == "__main__":
    unittest.main()
