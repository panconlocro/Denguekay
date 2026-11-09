"""Comparison helpers of denguekay.model.reproduce (no data needed)."""

import unittest

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


if __name__ == "__main__":
    unittest.main()
