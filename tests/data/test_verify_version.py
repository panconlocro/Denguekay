"""Per-version check of a pipeline run against the manifest of its Release."""

from pathlib import Path
from tempfile import TemporaryDirectory
import contextlib
import io
import unittest
import zipfile

from denguekay.data.ingestion.release_bundles import load_manifest, manifest_path
from denguekay.data.validation import frozen_inputs as frozen


class TestVerifyVersion(unittest.TestCase):
    def test_every_file_of_the_manifest_in_silver_and_gold_is_listed(self):
        with TemporaryDirectory() as temp:
            report = frozen.verify_version("v2", data_dir=temp)
        manifest = load_manifest(manifest_path("v2"))
        expected = {f["ruta"] for bundle in manifest["paquetes"] for f in bundle["archivos"]
                    if f["ruta"].startswith(("data/silver/", "data/gold/"))}
        self.assertEqual({item["ruta"] for item in report["archivos"]}, expected)
        self.assertEqual(set(report["faltan"]), expected)       # nothing was generated in the empty folder
        self.assertFalse(report["exito"])

    def test_maps_members_to_the_data_folder_and_skips_the_rest(self):
        self.assertEqual(frozen._local_path("d", "data/silver/a/b.csv"), Path("d") / "silver" / "a" / "b.csv")
        self.assertEqual(frozen._local_path("d", "data/gold/respaldo_pre_b3/x"), Path("d") / "gold" / "respaldo_pre_b3" / "x")
        self.assertIsNone(frozen._local_path("d", "data/reference/catalogo.csv"))
        self.assertIsNone(frozen._local_path("d", "models/experimentos/x.csv"))

    def test_a_regenerated_file_is_explained_against_the_release_zip(self):
        release = "ubigeo,anio,semana,casos_Dengue\n200101,2026,1,5\n200101,2026,2,7\n".encode()
        regenerated = "ubigeo,anio,semana,casos_Dengue\n200101,2026,1,5\n200101,2026,2,9\n".encode()
        name = "data/silver/epi_sala_semanal.csv"
        with TemporaryDirectory() as temp:
            archive = Path(temp) / "datos.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr(name, release)
            folder = Path(temp) / "silver"
            folder.mkdir()
            (folder / "epi_sala_semanal.csv").write_bytes(regenerated)
            report = frozen.verify_version("v2", data_dir=temp, release_zip=archive)
        item = next(entry for entry in report["archivos"] if entry["ruta"] == name)
        self.assertEqual(item["estado"], "difiere")
        self.assertEqual(item["diferencia"]["filas_distintas"], 1)
        self.assertIn(name, report["diferencias_en_fuentes"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            frozen.print_version_report(report)
        self.assertIn("1 filas con conteo distinto", output.getvalue())

    def test_report_prints_in_a_cp1252_console(self):
        with TemporaryDirectory() as temp:
            report = frozen.verify_version("v1", data_dir=temp)
        console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
        with contextlib.redirect_stdout(console):
            frozen.print_version_report(report)
        console.flush()


if __name__ == "__main__":
    unittest.main()
