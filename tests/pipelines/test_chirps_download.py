"""Tests of the detached CHIRPS run (no network: the check and the download are replaced)."""

import unittest
from unittest.mock import patch

from denguekay.pipelines import chirps_download as cd


class TestRunner(unittest.TestCase):
    def test_checks_then_downloads_the_range(self):
        with patch.object(cd, "check_sample_days", return_value={"ok": True, "problemas": []}) as check, \
                patch.object(cd, "download_final", return_value={"estado": "completa"}) as download:
            out = cd.main(["--start", "2000-01-01", "--end", "2000-01-31"])
        self.assertEqual(out["estado"], "completa")
        self.assertEqual(list(check.call_args.args[0]), list(cd.SAMPLE_DAYS))
        download.assert_called_once_with("2000-01-01", "2000-01-31")

    def test_a_failed_check_downloads_nothing(self):
        with patch.object(cd, "check_sample_days", return_value={"ok": False, "problemas": ["x"]}), \
                patch.object(cd, "download_final") as download:
            with self.assertRaises(SystemExit):
                cd.main([])
        download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
