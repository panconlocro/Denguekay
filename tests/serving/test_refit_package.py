"""The refit package of ``paquete_dir`` between the PC and the Storage: complete, hash-checked and never half-written."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from denguekay.pipelines import v4_weekly
from denguekay.pipelines.v4_weekly import WeeklyError
from denguekay.serving import refit_package as refit
from denguekay.serving.storage import LocalStorage

FILES = {"booster.json": b'{"booster": 1}', "origen.csv": b"ubigeo\n200101\n", "oos.csv.gz": b"\x1f\x8b-datos"}
RELATIVE = "models/experimentos/mejora_modelo/v4_reajuste/ajuste_prueba"


def make_package(folder):
    folder = Path(folder)
    folder.mkdir(parents=True)
    for name, content in FILES.items():
        (folder / name).write_bytes(content)
    manifest = {"version": "v4-b3", "archivos": {name: hashlib.sha256(content).hexdigest()
                                                 for name, content in FILES.items()}}
    (folder / "paquete.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder


class TestRefitPackage(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = make_package(self.root / "origen" / "ajuste_prueba")
        self.storage = LocalStorage(self.root / "storage")
        self.destination = self.root / RELATIVE

    def test_a_package_goes_up_and_comes_down_identical(self):
        paths = refit.upload(self.storage, self.source)
        self.assertEqual(sorted(paths), sorted(f"modelos/reajustes/ajuste_prueba/{name}" for name in [*FILES, "paquete.json"]))
        written = refit.download(self.storage, self.destination)
        self.assertEqual(sorted(written), sorted([*FILES, "paquete.json"]))
        for name in [*FILES, "paquete.json"]:
            self.assertEqual((self.destination / name).read_bytes(), (self.source / name).read_bytes())

    def test_an_altered_file_is_rejected_and_nothing_is_left_in_the_destination(self):
        refit.upload(self.storage, self.source)
        self.storage.save("modelos/reajustes/ajuste_prueba/booster.json", b'{"booster": 2}')   # altered after the upload
        with self.assertRaisesRegex(refit.RefitPackageError, "booster.json.*SHA-256"):
            refit.download(self.storage, self.destination)
        self.assertFalse(self.destination.exists())   # no manifest, no files: the preflight still sees it as absent

    def test_a_missing_file_is_rejected_and_a_package_that_was_never_uploaded_says_how_to_upload_it(self):
        refit.upload(self.storage, self.source)
        (self.root / "storage" / "modelos" / "reajustes" / "ajuste_prueba" / "origen.csv").unlink()
        with self.assertRaisesRegex(refit.RefitPackageError, "origen.csv"):
            refit.download(self.storage, self.destination)
        with self.assertRaisesRegex(FileNotFoundError, "refit_package --subir"):
            refit.download(self.storage, self.root / "otra" / "no_subido")

    def test_a_local_file_that_does_not_match_its_manifest_is_not_uploaded(self):
        (self.source / "origen.csv").write_bytes(b"cambiado")
        with self.assertRaisesRegex(refit.RefitPackageError, "origen.csv"):
            refit.upload(self.storage, self.source)
        self.assertFalse((self.root / "storage" / "modelos" / "reajustes").exists())

    def test_ensure_does_nothing_without_the_option_or_when_the_folder_is_there(self):
        self.assertEqual(refit.ensure(self.storage, {}, root=self.root), {"estado": "no_aplica"})
        make_package(self.destination)
        self.assertEqual(refit.ensure(self.storage, {"paquete_dir": RELATIVE}, root=self.root)["estado"], "ya_estaba")

    def test_ensure_downloads_a_missing_folder_and_tells_when_the_storage_does_not_have_it(self):
        options = {"paquete_dir": RELATIVE}
        self.assertEqual(refit.ensure(self.storage, options, root=self.root)["estado"], "no_esta_en_el_storage")
        refit.upload(self.storage, self.source)
        result = refit.ensure(self.storage, options, root=self.root)
        self.assertEqual(result["estado"], "descargado")
        self.assertTrue((self.destination / "paquete.json").is_file())


class TestWeeklyStep(unittest.TestCase):
    """What the weekly update does with it before its preflight."""

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.storage = LocalStorage(self.root / "storage")
        refit.upload(self.storage, make_package(self.root / "origen" / "ajuste_prueba"))

        class Config:
            opciones = {"paquete_dir": RELATIVE}

        self.cfg = Config()

    def test_a_correct_package_is_accepted_and_an_altered_one_stops_the_run_in_the_preflight(self):
        with patch.object(v4_weekly, "ROOT", self.root):
            self.assertEqual(v4_weekly.step_ensure_package(self.cfg, self.storage)["estado"], "descargado")
        altered = LocalStorage(self.root / "storage2")
        refit.upload(altered, make_package(self.root / "origen2" / "ajuste_prueba"))
        altered.save("modelos/reajustes/ajuste_prueba/origen.csv", b"alterado")
        with patch.object(v4_weekly, "ROOT", self.root / "otra_raiz"):
            with self.assertRaises(WeeklyError) as error:
                v4_weekly.step_ensure_package(self.cfg, altered)
        self.assertEqual(error.exception.step, "preflight")
        self.assertIn("rechazado", str(error.exception))
        self.assertFalse((self.root / "otra_raiz" / RELATIVE).exists())


if __name__ == "__main__":
    unittest.main()
