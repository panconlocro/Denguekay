"""Comparison helpers of denguekay.model.reproduce (no data needed)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from denguekay.config import paths
from denguekay.model import reproduce as rp


class TestJsonDifferences(unittest.TestCase):
    def test_equal_documents_have_no_differences(self):
        doc = {"a": 1.5, "b": [1, 2, {"c": "x"}], "fecha_corrida": "2026-11-09"}
        self.assertEqual(rp._json_differences(doc, dict(doc)), [])

    def test_numbers_strings_and_keys(self):
        a = {"a": 1.0, "b": "base_6", "c": 2, "fecha": "hoy"}
        b = {"a": 1.25, "b": "base_4", "d": 2, "fecha": "ayer"}
        paths = [p for p, _ in rp._json_differences(a, b)]
        self.assertIn("/a", paths)
        self.assertIn("/b", paths)
        self.assertIn("/c", paths)
        self.assertIn("/d", paths)
        self.assertNotIn("/fecha", paths)  # run metadata is not a result

    def test_largest_first(self):
        diffs = rp._json_differences({"x": 1.0, "y": 1.0}, {"x": 1.5, "y": 4.0})
        self.assertEqual(diffs[0][0], "/y")


class TestFrozenBruteRule(unittest.TestCase):
    """v1 ships only the manifest of the gold before the cleanup (gold/respaldo_pre_b3)."""

    def read_rule(self, with_clean_manifest):
        seen = {}

        def stop(panel, rule):
            seen["rule"] = rule
            raise RuntimeError("stop")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "backup").mkdir()
            (root / "backup" / "manifest_fase6.json").write_text(json.dumps({"regla_brote": {"origen": "respaldo"}}))
            clean = root / "manifest_fase6.json"
            if with_clean_manifest:
                clean.write_text(json.dumps({"regla_brote": {"origen": "limpio"}}))
            with patch.object(paths, "GOLD_MANIFEST", clean), patch.object(paths, "GOLD_BACKUP", root / "backup"),                     patch("denguekay.data.loading.load_integrated", return_value=None),                     patch("denguekay.evaluation.variants.inputs", side_effect=stop):
                with self.assertRaises(RuntimeError):
                    rp.frozen("V1")
        return seen["rule"]

    def test_uses_the_clean_gold_manifest_when_present(self):
        self.assertEqual(self.read_rule(True), {"origen": "limpio"})

    def test_falls_back_to_the_manifest_of_the_gold_before_the_cleanup(self):
        self.assertEqual(self.read_rule(False), {"origen": "respaldo"})


if __name__ == "__main__":
    unittest.main()
