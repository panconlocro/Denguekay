"""Tests of the Niño 1+2 ingestion and parsing (no network)."""

import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from denguekay.data.ingestion import enso
from denguekay.data.processing import enso_index as ei

TEXT = (" YR MON  NINO1+2   ANOM   NINO3    ANOM   NINO4    ANOM NINO3.4    ANOM\n"
        "1982   1   24.28   -0.24   25.84    0.17   28.01   -0.21   26.65    0.08\n"
        "1982   2   25.38   -0.72   26.26   -0.11   27.99   -0.11   26.54   -0.20\n")


class TestParse(unittest.TestCase):
    def test_parse_and_availability(self):
        t = ei.nino12_monthly(TEXT)
        self.assertEqual(t.nino12.tolist(), [24.28, 25.38])
        self.assertEqual(t.nino12_anom.tolist(), [-0.24, -0.72])
        self.assertEqual(t.fecha_disponible.tolist(), [pd.Timestamp("1982-02-10"), pd.Timestamp("1982-03-10")])

    def test_rejects_gaps_and_bad_rows(self):
        gap = TEXT + "1982   4   26.0   0.1   27.0   0.1   28.0   0.1   27.0   0.1\n"
        with self.assertRaises(ValueError):
            ei.parse_sstoi(gap)
        with self.assertRaises(ValueError):
            ei.parse_sstoi(TEXT + "1982   3   26.0\n")


class TestDownload(unittest.TestCase):
    def test_saves_by_date_and_never_overwrites(self):
        r = MagicMock(text=TEXT)
        with tempfile.TemporaryDirectory() as tmp, patch.object(enso.requests, "get", return_value=r):
            path = enso.download_sstoi(Path(tmp), today=dt.date(2026, 11, 3))
            self.assertEqual(path.name, "sstoi_20261103.indices")
            self.assertEqual(path.read_text(encoding="utf-8"), TEXT)
            with self.assertRaises(FileExistsError):
                enso.download_sstoi(Path(tmp), today=dt.date(2026, 11, 3))

    def test_rejects_an_unexpected_header(self):
        r = MagicMock(text="something else\n1 2 3\n")
        with tempfile.TemporaryDirectory() as tmp, patch.object(enso.requests, "get", return_value=r):
            with self.assertRaises(RuntimeError):
                enso.download_sstoi(Path(tmp), today=dt.date(2026, 11, 3))


if __name__ == "__main__":
    unittest.main()
