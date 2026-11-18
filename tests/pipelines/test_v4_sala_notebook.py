"""Run the Sala notebook with simulated public chart responses and a real kernel."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import nbformat
from nbclient import NotebookClient
import pandas as pd

from denguekay.pipelines.run_all import NOTEBOOKS

SETUP = """
import json
import os
from pathlib import Path
from denguekay.pipelines import v4_inputs

os.environ["DENGUEKAY_V4_OFFLINE"] = "0"
v4_inputs.BRONZE_SALA = Path("bronze")
v4_inputs.V4_SALA = Path("silver/confirmed.csv")
v4_inputs.UBIGEO_CATALOG = Path("catalogo.csv")
v4_inputs.UBIGEO_CATALOG.write_text("provincia,distrito,ubigeo\\nPiura,Piura,200101\\n", encoding="utf-8")

async def fake_scrape(year, targets, folder):
    assert targets == {("PIURA", "PIURA")}
    folder.mkdir(parents=True, exist_ok=True)
    week = f"{year}-01"
    chart = {"title": [{"text": "Tendencia semanal de casos segun tipo de diagnostico"}],
             "xAxis": [{"data": [week]}],
             "series": [{"name": "CONFIRMADO", "data": [{"value": [week, 5]}]},
                        {"name": "PROBABLE", "data": [{"value": [week, 99]}]}]}
    for level in ("departamento", "provincia", "distrito"):
        record = {"anio": year, "tipo_dx": "C", "nivel": level, "provincia": "PIURA", "distrito": "PIURA",
                  "chart": {"x": {"opts": chart}}}
        (folder / f"{level}.json").write_text(json.dumps(record), encoding="utf-8")

v4_inputs.scrape_sala = fake_scrape
"""


class TestSalaNotebook(unittest.TestCase):
    def test_download_path_runs_in_notebook_kernel(self):
        notebook = nbformat.read(NOTEBOOKS / "V4" / "05_bronze_sala.ipynb", as_version=4)
        notebook.cells.insert(0, nbformat.v4.new_code_cell(SETUP))
        with TemporaryDirectory() as temp:
            NotebookClient(notebook, timeout=60, resources={"metadata": {"path": temp}}).execute()
            data = pd.read_csv(Path(temp) / "silver" / "confirmed.csv", dtype={"ubigeo": "string"})
        self.assertFalse(data.empty)
        self.assertEqual(set(data.ubigeo), {"200101"})
        self.assertEqual(set(data.casos_Dengue), {5})
        self.assertEqual(set(data.tipo_dx), {"C"})
