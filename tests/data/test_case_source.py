"""Case source and coverage state of the V4 observations (HU0004-1, HU0001-1): only the labels change, never the counts."""

import unittest

import pandas as pd

from denguekay.data.processing.case_source import case_labels, case_source, has_source_record

HISTORY = pd.DataFrame({"ubigeo": ["200101", "200101", "200102"], "anio": [2024, 2024, 2024],
                        "semana": [1, 2, 1], "casos_Dengue": [0, 5, 3]})   # a recorded zero: ubigeo 200101, week 1
SALA = pd.DataFrame({"ubigeo": ["200101", "200101", "200102", "200101"], "anio": [2025, 2025, 2025, 2024],
                     "semana": [1, 2, 1, 40], "casos_Dengue": [0, 0, 2, 9]})   # the 2024 row is outside the Sala years


def panel(*keys):
    return pd.DataFrame([{"ubigeo": u, "anio": y, "semana": w, "casos_Dengue": 0} for u, y, w in keys])


class TestCaseSource(unittest.TestCase):
    def test_the_source_is_open_data_before_2025_and_the_sala_from_2025(self):
        self.assertEqual(case_source(2017), "datos_abiertos_confirmados")
        self.assertEqual(case_source(2024), "datos_abiertos_confirmados")
        self.assertEqual(case_source(2025), "sala_situacional")
        self.assertEqual(case_source(2026), "sala_situacional")

    def test_a_week_with_a_record_and_zero_cases_is_verified_with_zero_cases(self):
        frame = panel(("200101", 2024, 1))
        labels = case_labels(frame, HISTORY, SALA)
        self.assertEqual(labels.estado_cobertura.tolist(), ["verificado"])
        self.assertEqual(frame.casos_Dengue.tolist(), [0])   # the counts are not touched

    def test_a_week_without_a_record_is_sin_registro_and_keeps_zero_cases(self):
        frame = panel(("200102", 2024, 2), ("200103", 2024, 1))
        labels = case_labels(frame, HISTORY, SALA)
        self.assertEqual(labels.estado_cobertura.tolist(), ["sin_registro", "sin_registro"])
        self.assertEqual(frame.casos_Dengue.tolist(), [0, 0])

    def test_the_sala_explicit_zero_is_verified_and_a_missing_sala_week_is_not(self):
        frame = panel(("200101", 2025, 1), ("200101", 2025, 3))
        self.assertEqual(case_labels(frame, HISTORY, SALA).estado_cobertura.tolist(), ["verificado", "sin_registro"])

    def test_each_year_reads_only_its_own_source(self):
        # 2024 week 40 exists only in the Sala frame (outside its years); 2025 week 2 of 200102 only nowhere.
        frame = panel(("200101", 2024, 40), ("200101", 2025, 1), ("200101", 2024, 2))
        labels = case_labels(frame, HISTORY, SALA)
        self.assertEqual(labels.estado_cobertura.tolist(), ["sin_registro", "verificado", "verificado"])
        self.assertEqual(labels.fuente_casos.tolist(),
                         ["datos_abiertos_confirmados", "sala_situacional", "datos_abiertos_confirmados"])

    def test_the_index_of_the_frame_is_kept(self):
        frame = panel(("200101", 2024, 1), ("200101", 2024, 2)).set_index(pd.Index([10, 20]))
        record = has_source_record(frame, HISTORY, SALA)
        self.assertEqual(record.index.tolist(), [10, 20])
        self.assertTrue(record.all())


if __name__ == "__main__":
    unittest.main()
