"""Hash verification of the Release data bundles (no network)."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from denguekay.data.ingestion import release_bundles as rb


class TestReleaseBundles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "origen"
        (self.root / "data" / "silver").mkdir(parents=True)
        self.csv = self.root / "data" / "silver" / "a.csv"
        self.csv.write_text("ubigeo,casos\n200101,3\n200104,0\n", encoding="utf-8")
        self.zip = Path(self.tmp.name) / "datos.zip"
        self.entry = rb.build_bundle([self.csv], self.zip, "data", self.root)
        self.destination = Path(self.tmp.name) / "clon"

    def tearDown(self):
        self.tmp.cleanup()

    def test_manifest_entry(self):
        f = self.entry["archivos"][0]
        self.assertEqual((f["ruta"], f["filas"]), ("data/silver/a.csv", 2))
        self.assertEqual(f["sha256"], rb.sha256_file(self.csv))

    def test_extract_verifies_and_is_idempotent(self):
        report = rb.extract_bundle(self.zip, self.entry, self.destination)
        self.assertEqual(report["extraidos"], 1)
        self.assertEqual((self.destination / "data/silver/a.csv").read_bytes(), self.csv.read_bytes())
        self.assertEqual(rb.extract_bundle(self.zip, self.entry, self.destination)["ya_estaban"], 1)

    def test_wrong_zip_hash_is_rejected(self):
        bad = {**self.entry, "sha256": "0" * 64}
        with self.assertRaises(rb.BundleError):
            rb.extract_bundle(self.zip, bad, self.destination)
        self.assertFalse((self.destination / "data").exists())

    def test_wrong_file_hash_is_rejected(self):
        files = [{**self.entry["archivos"][0], "sha256": "0" * 64}]
        with self.assertRaises(rb.BundleError):
            rb.extract_bundle(self.zip, {**self.entry, "archivos": files}, self.destination)
        self.assertFalse((self.destination / "data/silver/a.csv").exists())

    def test_different_existing_file_needs_overwrite(self):
        target = self.destination / "data/silver/a.csv"
        target.parent.mkdir(parents=True)
        target.write_text("otro\n", encoding="utf-8")
        with self.assertRaises(rb.BundleError):
            rb.extract_bundle(self.zip, self.entry, self.destination)
        self.assertEqual(rb.extract_bundle(self.zip, self.entry, self.destination, overwrite=True)["sobrescritos"], 1)

    def test_member_outside_destination_is_rejected(self):
        evil = Path(self.tmp.name) / "malo.zip"
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("../fuera.csv", "x\n")
        entry = {"nombre": "malo.zip", "sha256": rb.sha256_file(evil), "destino": "data",
                 "archivos": [{"ruta": "../fuera.csv", "sha256": "0" * 64}]}
        with self.assertRaises(rb.BundleError):
            rb.extract_bundle(evil, entry, self.destination)

    def test_several_destinations(self):
        other = self.root / "models" / "experimentos" / "b.csv"
        other.parent.mkdir(parents=True)
        other.write_text("x\n1\n", encoding="utf-8")
        zip_path = Path(self.tmp.name) / "dos.zip"
        entry = rb.build_bundle([self.csv, other], zip_path, ["data", "models/experimentos"], self.root)
        self.assertEqual(rb.extract_bundle(zip_path, entry, self.destination)["extraidos"], 2)
        with self.assertRaises(rb.BundleError):
            rb.verify_bundle(zip_path, {**entry, "destino": "data"})

    def test_release_url(self):
        self.assertEqual(rb.release_url("o/r", "model/v3", "d.zip"),
                         "https://github.com/o/r/releases/download/model/v3/d.zip")


if __name__ == "__main__":
    unittest.main()
