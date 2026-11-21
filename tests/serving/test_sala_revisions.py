"""Phase 6 diagnosis (HU0019-1, OE2 §3.6): what the V4 load does today with a Sala correction of a week the frozen panel has.

These tests describe the CURRENT behaviour, so that the decision of the team (apply the revisions to the database, or
keep the frozen panel as an explicit rule) changes them on purpose. Case of the diagnosis: Piura (200101), epidemiological
week 1 of 2025, 4 cases in the frozen panel and 5 in a corrected Sala."""

import unittest

from denguekay.features.long_history import sala_after_panel
from serving.test_v4_case_labels import history, panel, run_prepare, sala

KEY = ("200101", 202501)


def panel_with_four_cases():
    frame = panel()
    frame.loc[frame.ubigeo.eq("200101") & frame.anio.eq(2025) & frame.semana.eq(1), "casos_Dengue"] = 4
    return frame


def sala_with_a_correction(cases):
    frame = sala()
    frame.loc[frame.ubigeo.eq("200101") & frame.anio.eq(2025) & frame.semana.eq(1), "casos_Dengue"] = cases
    return frame


class TestSalaCorrectionOfAFrozenWeek(unittest.TestCase):
    def test_sala_after_panel_drops_every_key_that_the_panel_already_has(self):
        extra, _ = sala_after_panel(panel_with_four_cases(), sala_with_a_correction(5), provisional=0)
        keys = set(zip(extra.ubigeo, extra.anio, extra.semana))
        self.assertNotIn(("200101", 2025, 1), keys)                     # the corrected week is a panel key: dropped
        self.assertEqual(sorted({(a, s) for _, a, s in keys}), [(2025, 2), (2025, 3)])   # only weeks the panel lacks

    def test_the_load_keeps_the_frozen_four_cases_when_the_sala_says_five(self):
        records = {(r["ubigeo"], r["id_semana"]): r
                   for r in run_prepare(panel_with_four_cases(), history(), sala_with_a_correction(5)).observaciones}
        self.assertEqual(records[KEY]["casos_dengue"], 4)

    def test_a_new_week_of_the_sala_does_enter(self):
        records = {(r["ubigeo"], r["id_semana"]): r
                   for r in run_prepare(panel_with_four_cases(), history(), sala_with_a_correction(5)).observaciones}
        self.assertIn(("200101", 202503), records)     # weeks after the panel come from the Sala


if __name__ == "__main__":
    unittest.main()
