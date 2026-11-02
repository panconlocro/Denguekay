"""Demo database command (decision D1): where it may write and how it isolates MLflow."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from denguekay.config.paths import DATA
from denguekay.serving import demo_database as demo


class TestDemoDatabase(unittest.TestCase):
    def test_never_writes_in_data(self):
        with self.assertRaises(ValueError):
            demo.build(DATA / "demo")

    def test_refuses_to_overwrite_without_replace(self):
        with tempfile.TemporaryDirectory() as name:
            (Path(name) / demo.DEMO_DB_NAME).write_bytes(b"")
            with self.assertRaises(FileExistsError):
                demo.build(name)
            self.assertEqual(demo.main(["--salida", name]), 1)

    def test_tracking_store_is_the_demo_folder_and_is_restored(self):
        with tempfile.TemporaryDirectory() as name, mock.patch.dict(os.environ, {"MLFLOW_TRACKING_URI": "sqlite:///otro.db"}):
            with demo.tracking_store(Path(name)):
                self.assertEqual(os.environ["MLFLOW_TRACKING_URI"], f"sqlite:///{(Path(name) / 'mlflow.db').as_posix()}")
            self.assertEqual(os.environ["MLFLOW_TRACKING_URI"], "sqlite:///otro.db")

    def test_build_migrates_and_publishes_into_the_folder(self):
        """publish is replaced: the full publication needs data/ and is covered by tests/serving/test_publish.py."""
        summary = {"fecha_corte_datos": "2025-12-27", "versiones": [{"codigo": "clf-h2-v1"}],
                   "inferencias_vigentes": [{"horizonte": 2, "id_semana_corte": 202552, "disponibles": 65, "otro": 1}]}
        with tempfile.TemporaryDirectory() as name:
            (Path(name) / "storage").mkdir()
            with mock.patch("denguekay.serving.publish.publish", return_value=summary) as publish:
                result = demo.build(name, replace=True)
            self.assertTrue((Path(name) / demo.DEMO_DB_NAME).is_file())
            self.assertEqual(result["versiones"], ["clf-h2-v1"])
            self.assertEqual(result["inferencias_vigentes"], [{"horizonte": 2, "id_semana_corte": 202552, "disponibles": 65}])
            self.assertEqual(publish.call_args.kwargs["storage"].root, Path(name).resolve() / "storage")


if __name__ == "__main__":
    unittest.main()
