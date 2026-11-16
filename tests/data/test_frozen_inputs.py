"""Published checksums apply per version, even when Releases share a relative path."""

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from denguekay.data.validation import frozen_inputs


class TestFrozenInputs(unittest.TestCase):
    def test_reports_each_version_without_writing(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "gold.csv"
            source.write_bytes(b"first version")
            masks = {}
            original = sha256(source.read_bytes()).hexdigest()
            for version, expected in (("v2", original), ("v4", "0" * 64)):
                masks[version] = root / f"{version}.json"
                masks[version].write_text(json.dumps({"paquetes": [{
                    "nombre": f"datos_{version}.zip", "archivos": [
                        {"ruta": "gold.csv", "sha256": expected}, {"ruta": "missing.csv", "sha256": expected},
                    ],
                }]}), encoding="utf-8")
            paths_before = {path.name: path.read_bytes() for path in root.iterdir()}
            with patch.object(frozen_inputs, "manifest_path", side_effect=masks.__getitem__):
                report = frozen_inputs.verify_frozen_inputs(root, ("v2", "v4"))
            self.assertEqual([x["estado"] for x in report["v2"]], ["coincide", "falta"])
            self.assertEqual([x["estado"] for x in report["v4"]], ["difiere", "falta"])
            self.assertEqual({path.name: path.read_bytes() for path in root.iterdir()}, paths_before)
