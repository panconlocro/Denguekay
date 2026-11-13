"""Historical MINSA CSV: confirmed counts with district-week keys."""

from pathlib import Path
import tempfile
import unittest

import pandas as pd

from denguekay.data.processing.epi_cases import build_weekly_cases, load_raw


class TestHistoricalCases(unittest.TestCase):
    def test_counts_only_piura_confirmed_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "DatosDengueV2.csv"
            source.write_text(
                "departamento,tipo_dx,ubigeo,ano,semana,extra\n"
                "PIURA,C,200101,2025,53,a\n"
                " Piura ,c,200101,2025,53,b\n"
                "PIURA,C,200104,2025,53,a\n"
                "PIURA,P,200101,2025,53,a\n"
                "PIURA,S,200101,2025,53,a\n"
                "LIMA,C,150101,2025,53,a\n",
                encoding="utf-8-sig",
            )
            result = build_weekly_cases(load_raw(source))

        self.assertEqual(result.to_dict("records"), [
            {"ubigeo": "200101", "anio": 2025, "semana": 53, "casos_Dengue": 2},
            {"ubigeo": "200104", "anio": 2025, "semana": 53, "casos_Dengue": 1},
        ])

    def test_invalid_confirmed_keys_fail_instead_of_losing_cases(self):
        row = {"departamento": "PIURA", "tipo_dx": "C", "ubigeo": "200101", "ano": 2025, "semana": 1}
        for column, value in (("ubigeo", "209999"), ("ano", None), ("semana", 1.5), ("semana", 54)):
            with self.subTest(column=column, value=value), self.assertRaises(ValueError):
                build_weekly_cases(pd.DataFrame([{**row, column: value}]))
