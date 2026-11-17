"""Notified-case ingestion of v0-v3 (restored from model/v3)."""

import hashlib
import os
import unittest

import pandas as pd

from denguekay.config.paths import BRONZE_EPI_EXCEL
from denguekay.data.processing.epi_cases_legacy import build_weekly_cases, deduplicate_cases, load_raw


class TestLegacyCases(unittest.TestCase):
    def test_counts_one_row_per_reported_case_and_keeps_ubigeo_a_string(self):
        raw = pd.DataFrame({"ubigeo": [200101, 200101, 200104], "distrito": ["Piura", "Piura", "Castilla"],
                            "ano": [2020, 2020, 2020], "semana": [1, 1, 2]})
        cases = build_weekly_cases(raw)
        self.assertEqual(list(cases.columns), ["ubigeo", "distrito", "anio", "semana", "casos_Dengue"])
        self.assertEqual(cases.set_index(["ubigeo", "semana"]).casos_Dengue.to_dict(),
                         {("200101", 1): 2, ("200104", 2): 1})

    def test_leading_zeros_of_ubigeo_are_restored(self):
        raw = pd.DataFrame({"ubigeo": ["20101"], "distrito": ["X"], "ano": [2020], "semana": [1]})
        self.assertEqual(build_weekly_cases(raw).ubigeo.iloc[0], "020101")

    def test_duplicated_district_weeks_are_added_up(self):
        cases = pd.DataFrame({"ubigeo": ["200101", "200101"], "distrito": ["Piura", "Piura (otro)"],
                              "anio": [2020, 2020], "semana": [1, 1], "casos_Dengue": [2, 3]})
        total = deduplicate_cases(cases)
        self.assertEqual(len(total), 1)
        self.assertEqual(int(total.casos_Dengue.iloc[0]), 5)

    @unittest.skipUnless(os.getenv("DENGUEKAY_TEST_LEGACY_EXCEL") == "1" and BRONZE_EPI_EXCEL.is_file(),
                         "Requires data/bronze/epi/PiuraDengue.xlsx and DENGUEKAY_TEST_LEGACY_EXCEL=1 (about 1 minute)")
    def test_excel_gives_the_historical_silver_of_v1_to_v3(self):
        cases = deduplicate_cases(build_weekly_cases(load_raw(BRONZE_EPI_EXCEL)))
        self.assertEqual(len(cases), 81196)
        payload = cases.to_csv(index=False, lineterminator="\r\n").encode("utf-8")
        self.assertTrue(hashlib.sha256(payload).hexdigest().startswith("c4b67ce03d6915d4"))


if __name__ == "__main__":
    unittest.main()
