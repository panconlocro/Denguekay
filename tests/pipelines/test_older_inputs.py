"""Steps of v0 to v3 that V4 does not have, and the per-version data folder of ``run_all``."""

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from denguekay.pipelines import older_inputs, run_all


class TestHistoricalSilver(unittest.TestCase):
    def test_counts_notified_cases_and_writes_the_bytes_of_the_release(self):
        raw = pd.DataFrame({"ubigeo": [200101, 200101, 200104], "distrito": ["Piura", "Piura", "Castilla"],
                            "ano": [2020, 2020, 2020], "semana": [1, 1, 2]})
        with TemporaryDirectory() as temp:
            excel, output = Path(temp) / "casos.xlsx", Path(temp) / "silver" / "epi_piura_semanal.csv"
            raw.to_excel(excel, index=False)
            with patch.object(older_inputs, "BRONZE_EPI_EXCEL", excel), \
                    patch.object(older_inputs, "SILVER_EPI_HISTORICAL", output):
                result = older_inputs.historical_silver()
            payload = output.read_bytes()
        self.assertEqual(result["filas"], 2)
        self.assertEqual(payload.decode().splitlines()[0], "ubigeo,anio,semana,casos_Dengue")
        self.assertIn(b"\r\n", payload)                      # written on Windows, as the frozen files
        self.assertNotIn(b"\n", payload.replace(b"\r\n", b""))


class TestVersionGold(unittest.TestCase):
    def test_each_version_persists_its_own_columns_and_horizons(self):
        self.assertEqual(older_inputs.VERSION_GOLD["v0"], older_inputs.VERSION_GOLD["v1"])
        self.assertEqual(older_inputs.VERSION_GOLD["v1"], ("candidatas", (2, 4)))
        self.assertEqual(older_inputs.VERSION_GOLD["v2"], ("v2", (2,)))
        self.assertEqual(older_inputs.VERSION_GOLD["v3"], ("v3", (2,)))

    def test_v0_and_v1_write_the_backup_folder_with_its_checksums(self):
        with TemporaryDirectory() as temp:
            backup, current = Path(temp) / "respaldo_pre_b3", Path(temp) / "gold"

            def fake_generate(path, folder, **options):
                folder.mkdir(parents=True)
                for name in ("manifest_fase6.json", "x_h2_gold.csv", "x_h4_gold.csv"):
                    (folder / name).write_bytes(name.encode())
                return {2: {"archivo": "x_h2_gold.csv", "filas": 1, "otro": 0}}

            with patch.object(older_inputs, "GOLD_BACKUP", backup), patch.object(older_inputs, "GOLD", current), \
                    patch.object(older_inputs, "generate_gold", side_effect=fake_generate) as generate:
                summary = older_inputs.generate_version_gold("v1")
            lines = (backup / "SHA256SUMS.txt").read_text().splitlines()
            self.assertEqual(generate.call_args.kwargs["columns"], "candidatas")
            self.assertEqual(generate.call_args.kwargs["horizons"], (2, 4))
            self.assertEqual([line.split("  ")[1] for line in lines],
                             ["manifest_fase6.json", "x_h2_gold.csv", "x_h4_gold.csv"])
            self.assertEqual(lines[0].split("  ")[0], hashlib.sha256(b"manifest_fase6.json").hexdigest())
            self.assertEqual(summary, {2: {"archivo": "x_h2_gold.csv", "filas": 1}})
            self.assertFalse(current.exists())

    def test_v2_writes_the_current_gold_folder_without_checksums(self):
        with TemporaryDirectory() as temp:
            backup, current = Path(temp) / "respaldo_pre_b3", Path(temp) / "gold"
            with patch.object(older_inputs, "GOLD_BACKUP", backup), patch.object(older_inputs, "GOLD", current), \
                    patch.object(older_inputs, "generate_gold", return_value={}) as generate:
                older_inputs.generate_version_gold("v2")
            self.assertEqual(generate.call_args.args[1], current)
            self.assertFalse((current / "SHA256SUMS.txt").exists())


class TestDataFolderPerVersion(unittest.TestCase):
    def run_step(self, version, inherited=None):
        with TemporaryDirectory() as temp, patch.object(run_all.subprocess, "run") as sub, \
                patch.dict(run_all.os.environ, {"DENGUEKAY_DATA_DIR": inherited} if inherited else {}, clear=False):
            sub.return_value.returncode = 0
            sub.return_value.stdout = sub.return_value.stderr = ""
            run_all.run(["01_bronze_geografia"], version=version, destination=Path(temp))
        return sub.call_args.kwargs["env"]

    def test_older_versions_write_apart_and_v4_owns_data(self):
        self.assertEqual(self.run_step("v2")["DENGUEKAY_DATA_DIR"], "data_anteriores/v2")
        self.assertEqual(self.run_step("v0")["DENGUEKAY_DATA_DIR"], "data_anteriores/v0")
        self.assertNotIn("DENGUEKAY_DATA_DIR", self.run_step("v4"))

    def test_v4_ignores_an_inherited_data_dir(self):
        self.assertNotIn("DENGUEKAY_DATA_DIR", self.run_step("v4", inherited="data_anteriores/v2"))

    def test_without_downloads_skips_the_sala_capture_of_older_versions_only(self):
        self.assertIn("05_bronze_sala", run_all.OLDER_DOWNLOAD_STEPS)
        self.assertNotIn("05_bronze_sala", run_all.DOWNLOAD_STEPS["v4"])

    def test_verification_options_stay_with_v4(self):
        with self.assertRaises(SystemExit):
            run_all.main(["--version", "v2", "--verificar"])


if __name__ == "__main__":
    unittest.main()
