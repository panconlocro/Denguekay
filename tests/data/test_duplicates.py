"""Repeated-key control of the epidemiological sources (HU0001-3): it returns its result and the rule applied."""

import contextlib
import io
import unittest

import pandas as pd

from denguekay.data.processing.epi_cases import DUPLICATE_RULE, deduplicate_cases, deduplicate_cases_with_report
from denguekay.data.validation.duplicates import duplicate_key_report


def cases():
    return pd.DataFrame({"ubigeo": ["200101", "200101", "200101", "200104"], "anio": [2024] * 4,
                         "semana": [1, 1, 2, 1], "casos_Dengue": [1, 2, 4, 5]})


class TestDuplicateKeyReport(unittest.TestCase):
    def test_it_lists_the_repeated_keys_and_the_rule(self):
        report = duplicate_key_report(cases(), source="fuente", rule="regla")
        self.assertEqual((report["claves_repetidas"], report["filas_con_llave_repetida"], report["filas"]), (1, 2, 4))
        self.assertEqual(report["ejemplos"], [{"ubigeo": "200101", "anio": 2024, "semana": 1, "filas": 2}])
        self.assertEqual((report["regla_aplicada"], report["resultado"]), ("regla", "con duplicados"))

    def test_without_repeated_keys_the_result_says_so(self):
        report = duplicate_key_report(cases().drop_duplicates(["ubigeo", "anio", "semana"]), source="f", rule="r")
        self.assertEqual((report["claves_repetidas"], report["ejemplos"], report["resultado"]),
                         (0, [], "sin duplicados"))

    def test_the_examples_are_limited_and_a_missing_key_column_fails(self):
        many = pd.DataFrame({"ubigeo": [f"2001{i:02d}" for i in range(30)] * 2, "anio": 2024, "semana": 1})
        self.assertEqual(len(duplicate_key_report(many, source="f", rule="r", sample=5)["ejemplos"]), 5)
        with self.assertRaisesRegex(ValueError, "faltan las columnas"):
            duplicate_key_report(cases().drop(columns="semana"), source="f", rule="r")


class TestDeduplicateCases(unittest.TestCase):
    def test_it_returns_the_control_with_the_documented_rule_and_adds_up_the_cases(self):
        total, control = deduplicate_cases_with_report(cases())
        self.assertEqual(total.sort_values(["ubigeo", "semana"]).casos_Dengue.tolist(), [3, 4, 5])
        self.assertEqual(control["claves_repetidas"], 1)
        self.assertEqual(control["regla_aplicada"], DUPLICATE_RULE)

    def test_the_old_function_still_prints_and_returns_the_same_cases(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            total = deduplicate_cases(cases())
        self.assertIn("2 filas con ubigeo-año-semana repetido", out.getvalue())
        pd.testing.assert_frame_equal(total, deduplicate_cases_with_report(cases())[0])


if __name__ == "__main__":
    unittest.main()
