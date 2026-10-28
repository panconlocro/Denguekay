"""ROOT must be the repository root wherever paths.py lives inside the package."""

import unittest

from denguekay.config import paths


class TestPaths(unittest.TestCase):
    def test_root_is_the_repository(self):
        self.assertTrue((paths.ROOT / "pyproject.toml").is_file())
        self.assertTrue((paths.ROOT / "alembic.ini").is_file())
        self.assertEqual(paths.DATA, paths.ROOT / "data")

    def test_config_file_exists(self):
        self.assertTrue(paths.CONFIG.is_file())


if __name__ == "__main__":
    unittest.main()
