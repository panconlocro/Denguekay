"""Provisional weeks of the Sala (HU0019-3): the cutoff is the last published week minus ``semanas_provisionales``.

The parameter lives in ``config.yaml`` (``serving.paquete.opciones.semanas_provisionales``, today 0: the operation uses
the last published week). The weeks that are left out are not loaded as observed and the archive of the emission names
them; with 0 the list is empty and no target is marked as provisional."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from v4_weekly_support import LiveCase
from denguekay.config.paths import CONFIG
from denguekay.features import long_history as lh
from denguekay.pipelines import v4_weekly
from denguekay.pipelines.v4_weekly import Options
from denguekay.serving.settings import service_settings


def sala():
    return pd.DataFrame({"ubigeo": ["200101"] * 5, "anio": [2025, 2025, 2026, 2026, 2026],
                         "semana": [52, 53, 1, 2, 3], "casos_Dengue": [1, 2, 3, 4, 5]})


def panel():
    return pd.DataFrame({"ubigeo": ["200101"], "anio": [2025], "semana": [52], "semana_inicio": ["2025-12-21"],
                         "casos_Dengue": [1]})


class TestCutoffRule(unittest.TestCase):
    def test_the_configured_operation_uses_the_last_published_week(self):
        self.assertEqual(service_settings(CONFIG, environ={}).opciones["semanas_provisionales"], 0)

    def test_the_cutoff_is_the_last_published_week_minus_the_provisional_ones(self):
        for provisional, last_loaded, dropped in ((0, (2026, 3), []), (1, (2026, 2), [(2026, 3)]),
                                                  (2, (2026, 1), [(2026, 2), (2026, 3)])):
            with self.subTest(provisional=provisional):
                after, left_out = lh.sala_after_panel(panel(), sala(), provisional=provisional)
                self.assertEqual(left_out, dropped)
                self.assertEqual((int(after.anio.iloc[-1]), int(after.semana.iloc[-1])), last_loaded)
                self.assertTrue(set(left_out).isdisjoint(zip(after.anio, after.semana)))   # never loaded as observed

    def test_the_weekly_step_reads_the_parameter_from_the_options(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "sala.csv").write_text(sala().to_csv(index=False), encoding="utf-8")
            (root / "panel.csv").write_text(panel().to_csv(index=False), encoding="utf-8")
            with patch.object(v4_weekly, "ROOT", root), patch.object(v4_weekly, "OPERATIONAL_SALA", root / "sala.csv"),                     patch.object(v4_weekly, "V4_INTEGRATED", root / "panel.csv"):
                results = {n: v4_weekly.step_expected_cutoff({"sala": "sala.csv", "semanas_provisionales": n})
                           for n in (0, 2)}
        self.assertEqual(results[0], (202603, 202603, []))
        self.assertEqual(results[2], (202601, 202603, [202602, 202603]))


class TestArchiveMarksTheProvisionalWeeks(LiveCase):
    def archived(self):
        (folder,) = list((self.base / "emisiones" / str(self.cutoff)).iterdir())
        return json.loads((folder / "emision.json").read_text(encoding="utf-8"))

    def test_with_two_provisional_weeks_the_archive_lists_them_and_marks_the_target_that_the_sala_published(self):
        report = self.run_weekly(Options(inicial=True))
        self.assertEqual(report["estado"], "emitida", report)
        record = self.archived()
        self.assertEqual(record["semanas_provisionales_excluidas"], [self.cutoff + 1, self.cutoff + 2])
        self.assertEqual({h: item["publicada_provisional_en_sala"] for h, item in record["objetivos"].items()},
                         {"2": True, "3": False, "4": False})

    def test_with_zero_provisional_weeks_nothing_is_excluded_or_marked(self):
        report = self.run_weekly(Options(inicial=True), expected_cutoff=lambda options: (self.cutoff, self.cutoff, []))
        self.assertEqual(report["estado"], "emitida", report)
        record = self.archived()
        self.assertEqual(record["semanas_provisionales_excluidas"], [])
        self.assertEqual(record["ultima_semana_sala_publicada"], self.cutoff)
        self.assertFalse(any(item["publicada_provisional_en_sala"] for item in record["objetivos"].values()))


if __name__ == "__main__":
    unittest.main()
