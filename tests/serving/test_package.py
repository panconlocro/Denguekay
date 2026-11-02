"""Model package (decision M2): content-addressed code, manifest, per-file SHA-256 and predictor cache."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from serving_support import preparar_muestra, sample_package
from denguekay.serving import package as pkg
from denguekay.serving.artifacts import InvalidArtifact, sha256_bytes
from denguekay.serving.predictors import load_predictor, predictor_module
from denguekay.serving.storage import LocalStorage

MEETS = {(h, t): False for h in (2, 4) for t in ("clasificacion", "regresion")}


class TestPackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg, protocol, trained = preparar_muestra()
        cls.package = sample_package(cfg, protocol, trained)

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.storage = LocalStorage(Path(self.folder.name))
        self.path, self.sha = pkg.save_package(self.storage, self.package, MEETS)

    def tearDown(self):
        self.folder.cleanup()

    def test_code_depends_only_on_content(self):
        self.assertEqual(pkg.package_code("v0", self.package.files), self.package.code)
        self.assertEqual(pkg.package_code("v0", dict(reversed(list(self.package.files.items())))), self.package.code)
        other = {**self.package.files, "h2_regresion.json": b"x"}
        self.assertNotEqual(pkg.package_code("v0", other), self.package.code)

    def test_round_trip_and_idempotent_save(self):
        loaded = pkg.load_package(self.storage, self.path, self.sha)
        self.assertEqual((loaded.kind, loaded.code, loaded.horizons, loaded.interval_level),
                         ("v0_compact_xgb", self.package.code, (2, 4), None))
        self.assertEqual(loaded.files, self.package.files)
        self.assertEqual(loaded.manifest["cumple_umbrales"]["2_clasificacion"], False)
        self.assertEqual(pkg.save_package(self.storage, self.package, MEETS), (self.path, self.sha))

    def test_rejects_altered_or_missing_manifest_or_file(self):
        with self.assertRaisesRegex(InvalidArtifact, "SHA-256"):
            pkg.load_package(self.storage, self.path, "0" * 64)
        booster = pkg.file_path(self.package.code, "h4_regresion.json")
        original = self.storage.read(booster)
        self.storage.save(booster, original + b" ")
        with self.assertRaisesRegex(InvalidArtifact, "h4_regresion.json.*SHA-256"):
            pkg.load_package(self.storage, self.path, self.sha)
        (Path(self.folder.name) / "modelos" / self.package.code / "h4_regresion.json").unlink()
        with self.assertRaisesRegex(InvalidArtifact, "No se encontró"):
            pkg.load_package(self.storage, self.path, self.sha)

    def save_manifest(self, changes):
        manifest = {**json.loads(self.storage.read(self.path)), **changes}
        content = pkg.manifest_bytes(manifest)
        self.storage.save("modelos/otro/manifest.json", content)
        return "modelos/otro/manifest.json", sha256_bytes(content)

    def test_rejects_unsupported_manifest_or_denguekay_version(self):
        for changes, message in (({"version_manifiesto": 99}, "no soportada"),
                                 ({"version_minima_denguekay": "99.0.0"}, "exige denguekay")):
            with self.subTest(changes=changes), self.assertRaisesRegex(InvalidArtifact, message):
                pkg.load_package(self.storage, *self.save_manifest(changes))
        path, _ = self.save_manifest({})
        self.storage.save(path, b"no es json")
        with self.assertRaises(InvalidArtifact):
            pkg.load_package(self.storage, path, sha256_bytes(b"no es json"))

    def test_unknown_type_and_predictor_cache(self):
        with self.assertRaisesRegex(InvalidArtifact, "desconocido"):
            predictor_module("inventado")
        loaded = pkg.load_package(self.storage, self.path, self.sha)
        first = load_predictor(loaded)
        self.assertIs(load_predictor(pkg.load_package(self.storage, self.path, self.sha)), first)
        self.assertEqual(first.horizons, (2, 4))
        without_booster = replace(loaded, sha256="f" * 64,
                                  files={k: v for k, v in loaded.files.items() if k != "h2_clasificacion.json"})
        with self.assertRaisesRegex(InvalidArtifact, "no trae"):
            load_predictor(without_booster)

    def test_denguekay_version_when_not_installed(self):
        with mock.patch.object(pkg, "version", side_effect=pkg.PackageNotFoundError):
            self.assertEqual(pkg.denguekay_version(), "0.0.0")


if __name__ == "__main__":
    unittest.main()
