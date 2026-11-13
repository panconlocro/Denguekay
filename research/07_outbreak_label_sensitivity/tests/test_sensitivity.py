"""Checks for the scenario definitions and reuse of archived prediction rows."""

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from run_sensitivity import align_labels, calibrate_seed, scenario_labels


class SensitivityTests(unittest.TestCase):
    def test_scenarios_share_targets_and_change_one_label_rule(self):
        rows = []
        for ubigeo, history, observed in (
            ("200101", [0, 0, 4, 4, 4], 6),
            ("200102", [0, 0, 4, 4, 4], 5),
            ("200103", [0, 0, 0, 0, 0], 1),
        ):
            for year, cases in enumerate([*history, observed], start=2000):
                jan4 = pd.Timestamp(year, 1, 4)
                sunday = jan4 - pd.Timedelta(days=(jan4.weekday() + 1) % 7)
                rows.append({"ubigeo": ubigeo, "anio": year, "semana": 10,
                             "semana_inicio": sunday + pd.Timedelta(weeks=9), "casos_Dengue": cases})
        series = pd.DataFrame(rows)
        principal = scenario_labels(series, 1.5, 5)
        a = scenario_labels(series, 2.0, 5)
        b = scenario_labels(series, 1.5, 3)
        keys = ["ubigeo", "semana_inicio", "casos_Dengue"]
        pd.testing.assert_frame_equal(principal[keys], a[keys])
        pd.testing.assert_frame_equal(principal[keys], b[keys])
        self.assertEqual(principal.brote.tolist(), [1, 0, 0])
        self.assertEqual(a.brote.tolist(), [0, 0, 0])
        self.assertEqual(b.brote.tolist(), [1, 1, 0])

    def test_alignment_preserves_overlapping_blocks_and_rejects_changed_counts(self):
        labels = pd.DataFrame({"ubigeo": ["200101"], "semana_inicio": [pd.Timestamp("2025-08-24")],
                               "casos_Dengue": [3], "brote": [1], "umbral_brote_casos": [2.0]})
        rows = pd.concat([labels, labels], ignore_index=True).assign(bloque=["calendario_2025", "temporada_2026"])
        self.assertEqual(align_labels(rows, labels).brote.tolist(), [1, 1])
        with self.assertRaisesRegex(ValueError, "conteos distintos"):
            align_labels(rows.assign(casos_Dengue=[3, 4]), labels)

    def test_calibration_excludes_earlier_block_labels_not_closed_at_origin(self):
        target = pd.date_range("2025-01-05", periods=4, freq="7D")
        rows = pd.DataFrame({"ubigeo": "200101", "anio": 2025, "semana": [2, 3, 4, 5],
                             "semana_inicio": target, "origen_cierre": target - pd.Timedelta(days=8),
                             "horizonte": 2, "bloque": ["anterior", "anterior", "anterior", "evaluado"],
                             "casos_Dengue": [0, 3, 4, 5], "brote": [0, 1, 1, 1],
                             "umbral_brote_casos": 2.0, "persistencia": 1, "estacional": 0,
                             "conteo_publicado": [0.5, 2.0, 3.0, 3.5], "probabilidad_cruda": [0.1, 0.8, 0.99, 0.6]})
        calibrated, fits = calibrate_seed(rows)
        fit = fits.set_index("bloque").loc["evaluado"]
        self.assertEqual(int(fit.filas_calibracion), 2)
        self.assertEqual(int(fit.positivos_calibracion), 1)
        self.assertEqual(int(fit.etiquetas_no_cerradas), 1)
        self.assertEqual(calibrated.casos_predichos.tolist(), rows.conteo_publicado.tolist())
        self.assertTrue(calibrated.probabilidad_calibrada.iloc[:3].isna().all())
        self.assertTrue(pd.notna(calibrated.probabilidad_calibrada.iloc[3]))


if __name__ == "__main__":
    unittest.main()
