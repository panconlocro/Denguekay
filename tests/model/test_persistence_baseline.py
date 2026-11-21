"""Persistence baseline of the V4 (HU0007-1): the rule, the check against the card and its MLflow run."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from denguekay.config.paths import V4_FROZEN
from denguekay.model import persistence_baseline as pb

# casos, persistencia (cases at the cutoff week), umbral de brote, brote, conteo de la V4
ROWS = [(10, 8, 5.0, 1, 9.0),    # persistence 8 > 5 and >= 2: alert, true positive
        (3, 1, 5.0, 0, 2.0),     # 1 is not above 5: no alert, true negative
        (1, 6, 5.0, 0, 1.0),     # 6 > 5: alert, false positive
        (9, 4, 5.0, 1, 7.0),     # 4 is not above 5: no alert, false negative
        (2, 1, 0.5, 1, 2.0)]     # 1 > 0.5 but below the minimum of 2 cases: no alert, false negative


def table(horizons=(2,)):
    frames = [pd.DataFrame(ROWS, columns=["casos_Dengue", "persistencia", "umbral_brote_casos", "brote",
                                          "casos_estimados"]).assign(horizonte=h) for h in horizons]
    return pd.concat(frames, ignore_index=True)


class TestRule(unittest.TestCase):
    def test_the_metrics_are_computed_by_hand(self):
        result = pb.evaluate(table())[2]
        # alerts: rows 1 and 3. TP = 1, FP = 1, FN = 2 -> precision 1/2, recall 1/3, F1 = 2 TP / (2 TP + FP + FN) = 2/5.
        self.assertEqual((result["n"], result["positivos"], result["alertas"]), (5, 3, 2))
        self.assertAlmostEqual(result["precision"], 0.5)
        self.assertAlmostEqual(result["recall"], 1 / 3)
        self.assertAlmostEqual(result["f1"], 0.4)
        # persistence errors: 2, 2, 5, 5, 1 -> MAE 15 / 5 = 3 and RMSE sqrt((4 + 4 + 25 + 25 + 1) / 5)
        self.assertAlmostEqual(result["mae"], 3.0)
        self.assertAlmostEqual(result["rmse"], (59 / 5) ** 0.5)
        # V4 errors: 1, 1, 0, 2, 0 -> MAE 0.8 and RMSE sqrt(6 / 5); the ratios use those of the persistence
        self.assertAlmostEqual(result["razon_mae_v4"], 0.8 / 3.0)
        self.assertAlmostEqual(result["razon_rmse_v4"], (6 / 5) ** 0.5 / (59 / 5) ** 0.5)

    def test_each_horizon_is_scored_apart(self):
        result = pb.evaluate(table((2, 3, 4)))
        self.assertEqual(sorted(result), [2, 3, 4])
        self.assertEqual({values["n"] for values in result.values()}, {5})

    def test_the_minimum_of_two_cases_is_part_of_the_alert(self):
        only_one = pd.DataFrame([(1, 1, 0.5, 1, 1.0)], columns=table().columns[:5].tolist()).assign(horizonte=2)
        result = pb.evaluate(only_one)[2]
        self.assertEqual(result["alertas"], 0)
        self.assertIsNone(result["razon_mae_v4"])     # persistence error 0: the ratio is not defined


class TestCheckAgainstTheCard(unittest.TestCase):
    def result(self, ratio_mae=0.868, ratio_rmse=0.861, rows=pb.EXPECTED_ROWS, positives=pb.EXPECTED_POSITIVES):
        return {2: {"n": rows, "positivos": positives, "razon_mae_v4": ratio_mae, "razon_rmse_v4": ratio_rmse}}

    PUBLISHED = {2: {"mae": 0.868, "rmse": 0.861}}

    def test_the_published_ratios_pass_and_the_differences_are_reported(self):
        self.assertEqual(pb.verify(self.result(0.8684, 0.8606), self.PUBLISHED), {2: {"mae": 0.0004, "rmse": -0.0004}})

    def test_a_ratio_that_differs_by_more_than_0_001_stops(self):
        with self.assertRaisesRegex(pb.BaselineMismatch, "h = 2.*MAE.*0.8700"):
            pb.verify(self.result(ratio_mae=0.870), self.PUBLISHED)
        with self.assertRaisesRegex(pb.BaselineMismatch, "RMSE"):
            pb.verify(self.result(ratio_rmse=0.8625), self.PUBLISHED)

    def test_a_block_that_is_not_the_published_one_stops(self):
        with self.assertRaisesRegex(pb.BaselineMismatch, "16965"):
            pb.verify(self.result(rows=16_964), self.PUBLISHED)
        with self.assertRaisesRegex(pb.BaselineMismatch, "2478"):
            pb.verify(self.result(positives=2_477), self.PUBLISHED)
        with self.assertRaisesRegex(pb.BaselineMismatch, "Horizontes"):
            pb.verify(self.result(), {2: self.PUBLISHED[2], 3: self.PUBLISHED[2]})


class TestMlflowRun(unittest.TestCase):
    REPORT = {"bloque": pb.BLOCK, "semilla": 17, "regla_alerta": "casos(t-h) > umbral y >= 2",
              "horizontes": {2: {"n": 5, "positivos": 3, "precision": 0.5, "recall": 1 / 3, "f1": 0.4, "mae": 3.0,
                                 "rmse": 3.4, "razon_mae_v4": 0.27, "razon_rmse_v4": 0.36},
                             3: {"n": 5, "positivos": 3, "precision": None, "recall": 0.0, "f1": None, "mae": 4.0,
                                 "rmse": 4.4, "razon_mae_v4": 0.3, "razon_rmse_v4": 0.4}},
              "insumos_sha256": {"observaciones.csv.gz": "a" * 64, "oos_b3_s17.csv.gz": "b" * 64}}

    def test_the_run_is_named_and_carries_the_five_metrics_the_seed_and_the_hashes(self):
        import mlflow

        with TemporaryDirectory(ignore_cleanup_errors=True) as folder:   # Windows keeps the SQLite file open
            uri = f"sqlite:///{(Path(folder) / 'mlflow.db').as_posix()}"
            run_id = pb.log_to_mlflow(self.REPORT, tracking_uri=uri)
            mlflow.set_tracking_uri(uri)
            parent = mlflow.get_run(run_id)
            self.assertEqual(parent.info.run_name, "persistencia · V4 · temporadas_2022_2026")
            self.assertEqual(parent.data.params["semilla"], "17")
            self.assertEqual(parent.data.tags["sha256.observaciones.csv.gz"], "a" * 64)
            for name in pb.METRICS:
                self.assertIn(f"h2.{name}", parent.data.metrics)
            self.assertAlmostEqual(parent.data.metrics["h2.precision"], 0.5)
            self.assertNotIn("h3.precision", parent.data.metrics)      # an undefined metric is not logged as 0
            self.assertAlmostEqual(parent.data.metrics["h3.recall"], 0.0)
            children = mlflow.search_runs(experiment_ids=[parent.info.experiment_id], output_format="list",
                                          filter_string=f"tags.mlflow.parentRunId = '{run_id}'")
            self.assertEqual(sorted(child.info.run_name for child in children),
                             ["h2 · persistencia", "h3 · persistencia"])
            mlflow.set_tracking_uri("")


@unittest.skipUnless((V4_FROZEN / "oos_b3_s17.csv.gz").is_file() and (V4_FROZEN / "observaciones.csv.gz").is_file(),
                     "Requires the frozen V4 package of the Release")
class TestWithTheRelease(unittest.TestCase):
    def test_it_reproduces_the_published_ratios_on_16965_rows_and_2478_positives_per_horizon(self):
        report = pb.build_report()
        for horizon, values in report["horizontes"].items():
            self.assertEqual((values["n"], values["positivos"]), (16_965, 2_478), horizon)
        for horizon, differences in report["diferencia_con_la_ficha"].items():
            self.assertTrue(all(abs(value) <= pb.TOLERANCE for value in differences.values()), horizon)
        self.assertEqual(json.loads(json.dumps(report))["semilla"], 17)


if __name__ == "__main__":
    unittest.main()
