"""ROOT must be the repository root wherever paths.py lives inside the package."""

import os
import subprocess
import sys
import unittest

from pathlib import Path

from denguekay.config import paths


class TestPaths(unittest.TestCase):
    def test_root_is_the_repository(self):
        self.assertTrue((paths.ROOT / "pyproject.toml").is_file())
        self.assertTrue((paths.ROOT / "alembic.ini").is_file())
        self.assertEqual(paths.DATA, paths.ROOT / "data")

    def test_config_file_exists(self):
        self.assertTrue(paths.CONFIG.is_file())

    def _paths_with(self, value):
        env = {key: item for key, item in os.environ.items() if key != "DENGUEKAY_DATA_DIR"}
        if value is not None:
            env["DENGUEKAY_DATA_DIR"] = value
        code = ("from denguekay.config import paths as p; "
                "print(p.SILVER, p.GOLD, p.GOLD_MANIFEST, p.SILVER_INTEGRATED, p.BRONZE, p.REFERENCE, "
                "p.GOLD_BACKUP, p.V4_GOLD, sep='|')")
        done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True,
                              cwd=paths.ROOT)
        return [Path(part) for part in done.stdout.strip().split("|")]

    def test_default_layout_is_unchanged(self):
        silver, gold, manifest, integrated, bronze, reference, backup, v4_gold = self._paths_with(None)
        self.assertEqual((silver, gold), (paths.ROOT / "data" / "silver", paths.ROOT / "data" / "gold"))
        self.assertEqual(self._paths_with("")[0], silver)   # an empty variable is the same as none

    def test_data_dir_moves_only_silver_and_gold(self):
        silver, gold, manifest, integrated, bronze, reference, backup, v4_gold = self._paths_with("data_anteriores/v2")
        base = paths.ROOT / "data_anteriores" / "v2"
        self.assertEqual((silver, gold), (base / "silver", base / "gold"))
        self.assertEqual(manifest, base / "gold" / "manifest_fase6.json")
        self.assertEqual(integrated, base / "silver" / "integrado" / "meteo_socio_epi_piura_2017_2025.csv")
        self.assertEqual(backup, base / "gold" / "respaldo_pre_b3")
        self.assertEqual(v4_gold.parent, base / "gold")
        self.assertEqual((bronze, reference), (paths.ROOT / "data" / "bronze", paths.ROOT / "data" / "reference"))


if __name__ == "__main__":
    unittest.main()
