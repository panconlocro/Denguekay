"""Cutoff of a frozen version trims each source to the extent of its Release."""

import unittest

import pandas as pd

from denguekay.pipelines.versions import V4_CUTOFF, clip_enso, clip_sala, clip_weekly


class TestCutoff(unittest.TestCase):
    def test_sala_keeps_through_week_43_of_2026(self):
        sala = pd.DataFrame({"anio": [2025, 2025, 2026, 2026, 2026], "semana": [52, 53, 1, 43, 44]})
        clipped = clip_sala(sala, V4_CUTOFF)
        self.assertEqual(list(zip(clipped.anio, clipped.semana)), [(2025, 52), (2025, 53), (2026, 1), (2026, 43)])

    def test_weekly_keeps_through_the_week_of_2026_10_25(self):
        weekly = pd.DataFrame({"semana_inicio": pd.to_datetime(["2026-10-18", "2026-10-25", "2026-11-01"])})
        self.assertEqual(len(clip_weekly(weekly, V4_CUTOFF)), 2)

    def test_enso_keeps_through_2026_10(self):
        enso = pd.DataFrame({"anio": [2025, 2026, 2026], "mes": [12, 10, 11]})
        self.assertEqual(len(clip_enso(enso, V4_CUTOFF)), 2)

    def test_no_cutoff_keeps_everything(self):
        frame = pd.DataFrame({"anio": [2030], "semana": [1], "mes": [1], "semana_inicio": ["2030-01-06"]})
        for clip in (clip_sala, clip_weekly, clip_enso):
            self.assertEqual(len(clip(frame, None)), 1)


if __name__ == "__main__":
    unittest.main()
