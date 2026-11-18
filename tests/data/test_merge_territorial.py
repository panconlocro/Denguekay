"""Territorial homologation (HU0003-2): the districts without correspondence or ambiguous are returned and named."""

import contextlib
import io
import unittest

import pandas as pd

from denguekay.data.processing.merge import diagnose_unmatched_districts, merge_meteo_socio
from denguekay.data.validation.integrated_expectations import validate_complete


def meteo(keys, province="Piura"):
    return pd.DataFrame({"provincia": province, "distrito": keys, "distrito_key": keys, "anio": 2024, "semana": 1})


def socio(keys, codes=None):
    codes = codes or [f"2001{i:02d}" for i in range(len(keys))]
    return pd.DataFrame({"ubigeo": codes, "departamento": "PIURA", "provincia": "Piura", "distrito": keys,
                         "distrito_key": keys, "anio": 2024, "poblacion": 100})


class TestDiagnose(unittest.TestCase):
    def test_it_returns_the_unmatched_and_the_ambiguous_districts_and_still_prints(self):
        weather = pd.concat([meteo(["A", "B", "C"]), meteo(["C"], province="Sullana")])
        census = socio(["A", "B", "D"]).pipe(lambda f: pd.concat([f, f.iloc[[0]].assign(ubigeo="209999")]))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            found = diagnose_unmatched_districts(weather, census)
        self.assertEqual(found, {"solo_en_meteo": ["C"], "solo_en_socio": ["D"], "ambiguos": ["A", "C"]})
        self.assertIn("En meteo pero no en socio", out.getvalue())

    def test_a_clean_correspondence_returns_empty_lists(self):
        found = diagnose_unmatched_districts(meteo(["A", "B"]), socio(["A", "B"]), echo=False)
        self.assertEqual(found, {"solo_en_meteo": [], "solo_en_socio": [], "ambiguos": []})


class TestMergeStops(unittest.TestCase):
    def test_the_merge_stops_and_names_the_districts(self):
        with self.assertRaises(ValueError) as error:
            merge_meteo_socio(meteo(["A", "B"]), socio(["A", "C"]))
        message = str(error.exception)
        self.assertIn("['B']", message)
        self.assertIn("['C']", message)

    def test_the_merge_stops_on_an_ambiguous_district(self):
        census = pd.concat([socio(["A"]), socio(["A"], codes=["209999"])])
        with self.assertRaisesRegex(ValueError, r"ambiguos \['A'\]"):
            merge_meteo_socio(meteo(["A"]), census)

    def test_a_clean_correspondence_merges_as_before(self):
        result = merge_meteo_socio(meteo(["A", "B"]), socio(["A", "B"]))
        self.assertEqual(len(result), 2)
        self.assertFalse(result.poblacion.isna().any())


class TestValidateCompleteNamesTheDistricts(unittest.TestCase):
    def test_the_error_carries_the_affected_districts_and_not_only_the_count(self):
        from denguekay.config.paths import V4_INTEGRATED

        if not V4_INTEGRATED.is_file():
            self.skipTest("el panel de la V4 no está en data/")
        from denguekay.data.loading import load_integrated
        from denguekay.data.validation.integrated_expectations import coverage_path, load_case_coverage

        panel = load_integrated(V4_INTEGRATED)
        coverage = load_case_coverage(coverage_path(V4_INTEGRATED))
        broken = panel.copy()
        broken.loc[broken.ubigeo.eq("200104").idxmax(), "temp_media"] = None
        with self.assertRaises(ValueError) as error:
            validate_complete(broken, coverage)
        self.assertIn("Dataset remains incomplete", str(error.exception))
        self.assertIn("distritos afectados", str(error.exception))
        self.assertIn("200104", str(error.exception))


if __name__ == "__main__":
    unittest.main()
