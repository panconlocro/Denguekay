"""HU0005-5: completeness over the fixed contractual calendar and with the three temperatures."""

import unittest

import pandas as pd

from denguekay.config.paths import UBIGEO_CATALOG
from denguekay.data.calendar import mmwr_epi_week
from denguekay.data.processing.epi_sala import load_ubigeo_catalog
from denguekay.data.validation import completeness_criterion as criterion
from denguekay.data.validation import quality_report as qr

DISTRICTS = load_ubigeo_catalog(UBIGEO_CATALOG).ubigeo.tolist()
WEEKS = criterion.contractual_week_starts()


def full_panel():
    """The 65 districts x the 469 contractual weeks, with every mandatory column filled (in memory only)."""
    index = pd.MultiIndex.from_product([DISTRICTS, WEEKS], names=["ubigeo", "semana_inicio"]).to_frame(index=False)
    weeks = mmwr_epi_week(index.semana_inicio)
    return index.assign(anio=weeks.anio_epi.to_numpy(), semana=weeks.semana_epi.to_numpy(), casos_Dengue=0,
                        temp_media=25.0, temp_min=20.0, temp_max=30.0, precip_total_mm=1.0, hum_rel_media=60.0,
                        poblacion=1000)


class TestCriterion(unittest.TestCase):
    def test_the_contractual_calendar_is_469_mmwr_weeks_from_2017_se1_to_2025_se52(self):
        self.assertEqual(len(WEEKS), 469)
        self.assertEqual((WEEKS[0].date().isoformat(), WEEKS[-1].date().isoformat()), ("2017-01-01", "2025-12-21"))
        weeks = mmwr_epi_week(pd.Series(WEEKS))
        self.assertEqual((int(weeks.anio_epi.iloc[0]), int(weeks.semana_epi.iloc[0])), (2017, 1))
        self.assertEqual((int(weeks.anio_epi.iloc[-1]), int(weeks.semana_epi.iloc[-1])), (2025, 52))
        self.assertEqual(len(DISTRICTS) * len(WEEKS), 30485)
        self.assertEqual(len(qr.expected_grid(DISTRICTS)), 30485)

    def test_the_three_temperatures_are_mandatory(self):
        self.assertLessEqual({"temp_media", "temp_min", "temp_max"}, set(criterion.MANDATORY.values()))
        self.assertIs(qr.MANDATORY, criterion.MANDATORY)   # one definition for the report and the tests


class TestFullPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel = full_panel()

    def test_the_complete_panel_is_30485_of_30485_and_conforming(self):
        measure = qr.completeness(self.panel, DISTRICTS)
        self.assertEqual((measure["filas_esperadas"], measure["filas_completas"]), (30485, 30485))
        self.assertEqual((measure["completitud"], measure["cumple"]), (1.0, True))

    def test_blanking_1800_values_of_a_temperature_gives_94_10_percent_and_names_the_variable(self):
        for column in ("temp_min", "temp_max"):
            with self.subTest(column=column):
                frame = self.panel.copy()
                frame.loc[frame.index[:1800], column] = None
                measure = qr.completeness(frame, DISTRICTS)
                self.assertEqual(measure["filas_completas"], 30485 - 1800)
                self.assertEqual(qr.percent(measure["completitud"]), "94,10 %")
                self.assertFalse(measure["cumple"])
                self.assertEqual([v for v, item in measure["por_variable"].items() if item["nulos"]], [column])
                self.assertEqual(measure["por_variable"][column]["nulos"], 1800)

    def test_removing_the_first_or_the_last_week_lowers_the_completeness_and_keeps_the_denominator(self):
        for week in (WEEKS[0], WEEKS[-1]):
            with self.subTest(week=week.date().isoformat()):
                measure = qr.completeness(self.panel[self.panel.semana_inicio.ne(week)], DISTRICTS)
                self.assertEqual(measure["filas_esperadas"], 30485)   # the period is not deduced from the data
                self.assertEqual((measure["filas_ausentes"], measure["filas_completas"]), (65, 30420))
                self.assertLess(measure["completitud"], 1.0)
                self.assertEqual(measure["periodo"]["semanas"], 469)

    def test_a_week_outside_the_period_does_not_count_and_is_reported(self):
        extra = self.panel[self.panel.semana_inicio.eq(WEEKS[-1])].assign(
            semana_inicio=WEEKS[-1] + pd.Timedelta(days=7), anio=2025, semana=53)
        measure = qr.completeness(pd.concat([self.panel, extra], ignore_index=True), DISTRICTS)
        self.assertEqual((measure["filas_esperadas"], measure["filas_completas"], measure["filas_fuera_del_periodo"]),
                         (30485, 30485, 65))

    def test_the_district_coverage_uses_the_same_calendar(self):
        coverage = qr.coverage_by_district(self.panel[self.panel.semana_inicio.ne(WEEKS[0])], None, None, DISTRICTS)
        self.assertEqual(coverage[DISTRICTS[0]]["semanas_esperadas"], 469)
        self.assertEqual(coverage[DISTRICTS[0]]["semanas_presentes"], 468)


if __name__ == "__main__":
    unittest.main()
