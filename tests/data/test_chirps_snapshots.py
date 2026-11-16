"""Historical CHIRPS reconstruction is gated by the observed archive time and Lima date."""

from contextlib import redirect_stdout
from datetime import datetime
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import pandas as pd

from denguekay.data.processing import chirps_snapshots as snapshots
from denguekay.data.processing.chirps_precipitation import SILVER_COLUMNS


PRELIM_CAPTURE = datetime.fromisoformat("2026-10-16T12:00:00-05:00")
FINAL_CAPTURE = datetime.fromisoformat("2026-11-16T15:00:00-05:00")


class TestChirpsSnapshots(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder = self.root / "capturas"
        self.prelim = pd.DataFrame([
            ("020101", "2026-10-04", 5.25, "prelim", "2026-10-15"),
            ("020101", "2026-10-11", 6.0, "prelim", "2026-10-17"),
        ], columns=SILVER_COLUMNS)
        self.final = self.prelim.assign(version="final", precip_total_mm=[9.75, 8.0])
        self.archived = snapshots.archive_snapshot(self.prelim, observed_at=PRELIM_CAPTURE, folder=self.folder)

    def test_final_cannot_replace_preliminary_at_an_earlier_cutoff(self):
        snapshots.archive_snapshot(self.final, observed_at=FINAL_CAPTURE, folder=self.folder)
        early, lineage = snapshots.snapshot_at(datetime.fromisoformat("2026-10-17T04:59:59+00:00"), folder=self.folder)
        self.assertEqual(early.ubigeo.tolist(), ["020101"])
        self.assertEqual(list(zip(early.version, early.precip_total_mm)), [("prelim", 5.25)])
        self.assertEqual(lineage["captura"], self.archived.name)
        late, _ = snapshots.snapshot_at(FINAL_CAPTURE, folder=self.folder)
        self.assertEqual(list(zip(late.version, late.precip_total_mm)), [("final", 9.75), ("final", 8.0)])

    def test_cutoff_cannot_predate_the_only_available_capture(self):
        with self.assertRaises(FileNotFoundError):
            snapshots.snapshot_at(datetime.fromisoformat("2026-10-15T23:59:59-05:00"), folder=self.folder)
        with self.assertRaises(ValueError):
            snapshots.snapshot_at(datetime(2026, 10, 17), folder=self.folder)

    def test_cli_exports_with_verifiable_lineage_and_protects_capture(self):
        with self.assertRaises(FileExistsError):
            snapshots.archive_snapshot(self.final, observed_at=PRELIM_CAPTURE, folder=self.folder)
        output = self.root / "al_corte"
        log = StringIO()
        cutoff = "2026-10-17T23:59:59-05:00"
        with patch.multiple(snapshots, ROOT=self.root, V4_CHIRPS_SNAPSHOTS=self.folder, V4_CHIRPS_CUTOFFS=output), \
                redirect_stdout(log):
            self.assertEqual(snapshots.main(["--corte", cutoff]), 0)
        report = json.loads(log.getvalue())
        saved = (self.root / report["salida"]).read_bytes()
        with ZipFile(self.archived) as archive:
            original = archive.read(snapshots.MANIFEST)
            payload = archive.read(snapshots.V4_CHIRPS.name)
        self.assertEqual(json.loads(original)["sha256"], sha256(payload).hexdigest())
        pd.testing.assert_frame_equal(pd.read_csv(self.root / report["salida"], dtype={"ubigeo": "string"}),
                                      self.prelim.astype({"ubigeo": "string"}))
        self.assertEqual(report["sha256_salida"], sha256(saved).hexdigest())
        self.assertEqual(report["sha256"], sha256(payload).hexdigest())
        self.assertEqual(report["filas"], 2)

    def test_tampered_capture_is_rejected(self):
        with ZipFile(self.archived) as original:
            manifest = original.read(snapshots.MANIFEST)
        with ZipFile(self.archived, "w") as updated:
            updated.writestr(snapshots.MANIFEST, manifest)
            updated.writestr(snapshots.V4_CHIRPS.name, b"modified")
        with self.assertRaisesRegex(ValueError, "Invalid CHIRPS snapshot lineage"):
            snapshots.snapshot_at(FINAL_CAPTURE, folder=self.folder)
