"""Rule of the V4 load: the Sala never corrects the frozen panel; the corrections it ignores are recorded (HU0019-1, §3.6).

The 2017-2025 panel of the frozen copy is the one the V4 was trained and calibrated with, verified by SHA-256 against the
Release. A Sala value that differs from it for a week the panel has is a revision that the weekly load ignores and lists in
``ejecucion.detalle`` and in ``emision.json`` (the total and the first 50). A correction of a week AFTER the panel is not
frozen: the next load applies it. Case of the diagnosis: Piura (200101), epidemiological week 1 of 2025, 4 cases in the
panel and 5 in a corrected Sala."""

from dataclasses import replace
import json
import unittest

import pandas as pd

from denguekay.db.models import Run
from denguekay.db.session import transaction
from denguekay.features.long_history import IGNORED_REVISIONS_LIMIT, ignored_sala_revisions, sala_after_panel
from denguekay.pipelines.v4_weekly import Options
from serving.test_v4_case_labels import history, panel, run_prepare, sala
from v4_weekly_support import LiveCase

KEY = ("200101", 202501)
REVISION = {"ubigeo": "200101", "anio": 2025, "semana": 1, "casos_panel": 4, "casos_sala": 5}


def set_cases(frame, ubigeo, year, week, cases):
    frame = frame.copy()
    frame.loc[frame.ubigeo.eq(ubigeo) & frame.anio.eq(year) & frame.semana.eq(week), "casos_Dengue"] = cases
    return frame


def panel_with_four_cases():
    return set_cases(panel(), "200101", 2025, 1, 4)


def sala_with(cases, year=2025, week=1):
    """The Sala agrees with the frozen panel on SE 1 (4 cases) except for the week that is set."""
    return set_cases(set_cases(sala(), "200101", 2025, 1, 4), "200101", year, week, cases)


def records_of(batch):
    return {(r["ubigeo"], r["id_semana"]): r for r in batch.observaciones}


class TestTheFrozenPanelIsNeverCorrected(unittest.TestCase):
    def test_sala_after_panel_drops_every_key_that_the_panel_already_has(self):
        extra, _ = sala_after_panel(panel_with_four_cases(), sala_with(5), provisional=0)
        keys = set(zip(extra.ubigeo, extra.anio, extra.semana))
        self.assertNotIn(("200101", 2025, 1), keys)                     # the corrected week is a panel key: dropped
        self.assertEqual(sorted({(a, s) for _, a, s in keys}), [(2025, 2), (2025, 3)])   # only weeks the panel lacks

    def test_the_load_ignores_the_correction_of_piura_se1_2025_and_records_it(self):
        batch = run_prepare(panel_with_four_cases(), history(), sala_with(5))
        self.assertEqual(records_of(batch)[KEY]["casos_dengue"], 4)     # the frozen value stays
        self.assertEqual(batch.revisiones_ignoradas,
                         {"total": 1, "mostradas": 1, "limite": IGNORED_REVISIONS_LIMIT, "revisiones": [REVISION]})

    def test_without_corrections_nothing_is_recorded(self):
        batch = run_prepare(panel_with_four_cases(), history(), sala_with(4))
        self.assertEqual(batch.revisiones_ignoradas,
                         {"total": 0, "mostradas": 0, "limite": IGNORED_REVISIONS_LIMIT, "revisiones": []})

    def test_a_correction_of_a_week_after_the_panel_is_applied_by_the_next_load(self):
        first = run_prepare(panel_with_four_cases(), history(), sala_with(0, week=2))
        second = run_prepare(panel_with_four_cases(), history(), sala_with(3, week=2))   # the Sala corrected SE 2
        self.assertEqual(records_of(first)[("200101", 202502)]["casos_dengue"], 0)
        self.assertEqual(records_of(second)[("200101", 202502)]["casos_dengue"], 3)
        self.assertEqual(second.revisiones_ignoradas["total"], 0)      # it is not a revision of the frozen panel


class TestTheRecord(unittest.TestCase):
    def frames(self, differing):
        districts = [f"2001{n:02d}" for n in range(1, 61)]
        rows = [{"ubigeo": u, "anio": 2025, "semana": week, "casos_Dengue": 1} for week in (3, 1, 2) for u in districts]
        base = pd.DataFrame(rows)
        revised = base.copy()
        revised.loc[revised.index[:differing], "casos_Dengue"] = 7
        return base, revised

    def test_with_more_than_50_it_keeps_the_total_and_the_first_50_in_order(self):
        base, revised = self.frames(differing=180)    # 60 districts x weeks 3, 1, 2: the first 180 rows are all of them
        result = ignored_sala_revisions(base, revised)
        self.assertEqual((result["total"], result["mostradas"], result["limite"]), (180, 50, 50))
        keys = [(r["anio"], r["semana"], r["ubigeo"]) for r in result["revisiones"]]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(keys[0], (2025, 1, "200101"))
        self.assertTrue(all((r["casos_panel"], r["casos_sala"]) == (1, 7) for r in result["revisiones"]))

    def test_ubigeo_is_compared_as_a_six_digit_string(self):
        base = pd.DataFrame({"ubigeo": ["200101"], "anio": [2025], "semana": [1], "casos_Dengue": [4]})
        revised = pd.DataFrame({"ubigeo": ["200101"], "anio": [2025], "semana": [1], "casos_Dengue": [5]})
        self.assertEqual(ignored_sala_revisions(base, revised)["revisiones"][0]["ubigeo"], "200101")


class TestTheEmissionCarriesIt(LiveCase):
    def test_the_report_the_archive_and_the_run_carry_the_ignored_revisions(self):
        ignored = {"total": 1, "mostradas": 1, "limite": IGNORED_REVISIONS_LIMIT, "revisiones": [REVISION]}
        self.current = replace(self.current, revisiones_ignoradas=ignored)
        report = self.run_weekly(Options(inicial=True))
        self.assertEqual(report["estado"], "emitida", report)
        self.assertEqual(report["revisiones_ignoradas"], 1)
        self.assertTrue(any("ignora por regla" in warning for warning in report["advertencias"]))
        record = json.loads((self.base / report["emision"] / "emision.json").read_text(encoding="utf-8"))
        self.assertEqual(record["revisiones_ignoradas"], ignored)
        with transaction(self.motor) as session:
            ingestion = session.get(Run, record["ejecuciones"]["ingesta"])
            self.assertEqual(ingestion.detalle["revisiones_ignoradas"], ignored)

    def test_without_corrections_the_report_has_a_zero_and_no_warning(self):
        report = self.run_weekly(Options(inicial=True))
        self.assertEqual(report["revisiones_ignoradas"], 0)
        self.assertFalse(any("ignora por regla" in warning for warning in report.get("advertencias", [])))


if __name__ == "__main__":
    unittest.main()
