"""Tests of denguekay.data.seasons with synthetic data (no data/ needed)."""

import unittest

import pandas as pd

from denguekay.data.seasons import assign_season


class TestSeasons(unittest.TestCase):
    def test_assign_season(self):
        t = assign_season(pd.Series([2022, 2022, 2023]), pd.Series([35, 36, 10]), week_start=36)
        self.assertEqual(t.tolist(), [2022, 2023, 2023])


if __name__ == "__main__":
    unittest.main()
