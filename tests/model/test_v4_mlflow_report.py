"""The MLflow report of the V4 package: every horizon has its variant and its folds (it used to log them empty)."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from denguekay.model.tracking import fold_metrics, variant_folds, variant_summary
from denguekay.serving.demo_b3_v4 import ACCEPTANCE_BLOCK, block_metrics, mlflow_horizons


def group(n=8):
    return pd.DataFrame({"brote": [1, 0] * (n // 2), "probabilidad_brote": [0.8, 0.3] * (n // 2),
                         "casos_Dengue": [5, 0] * (n // 2), "casos_estimados": [4.0, 1.0] * (n // 2),
                         "persistencia": [3, 1] * (n // 2)})


def by_horizon():
    blocks = ("temporada_2022", "temporada_2023", ACCEPTANCE_BLOCK)
    return {h: {block: block_metrics(block, group()) for block in blocks} for h in (2, 3, 4)}


class TestHorizonsOfTheReport(unittest.TestCase):
    def test_each_horizon_has_one_variant_with_one_fold_per_block(self):
        horizons = mlflow_horizons(by_horizon(), 17)
        self.assertEqual(sorted(horizons), ["2", "3", "4"])
        for horizon, block in horizons.items():
            (variant,) = block["variantes"]
            self.assertEqual(variant, "b3_obs_s17")
            folds = variant_folds(block["variantes"][variant])     # the walker of tracking.py finds them
            self.assertEqual([fold["bloque"] for fold in folds], ["temporada_2022", "temporada_2023", ACCEPTANCE_BLOCK])
            self.assertEqual({fold["horizonte"] for fold in folds}, {int(horizon)})

    def test_the_folds_carry_the_metrics_mlflow_logs_and_the_acceptance_block_is_not_a_validation_fold(self):
        folds = variant_folds(mlflow_horizons(by_horizon(), 17)["2"]["variantes"]["b3_obs_s17"])
        metrics, params = fold_metrics(folds[-1])
        for name in ("cls_precision", "cls_recall", "cls_f1", "cls_brier", "reg_mae", "reg_rmse", "pers_mae", "pers_rmse"):
            self.assertIn(name, metrics)
        self.assertEqual(params["tipo"], "agregado")
        self.assertEqual(variant_summary(folds).get("validacion_media.n_bloques"), None)   # test blocks, never averaged

    def test_a_block_without_its_size_still_makes_a_fold(self):
        horizons = mlflow_horizons({2: {"temporada_2022": {"clasificacion": {}, "regresion": {}}}}, 17)
        (fold,) = variant_folds(horizons["2"]["variantes"]["b3_obs_s17"])
        self.assertNotIn("n_prueba", fold)

    def test_the_block_metrics_are_the_ones_of_the_versions_and_are_not_recalculated(self):
        source = by_horizon()
        folds = variant_folds(mlflow_horizons(source, 17)["3"]["variantes"]["b3_obs_s17"])
        self.assertEqual(folds[0]["regresion"], source[3]["temporada_2022"]["regresion"])
        self.assertEqual(folds[0]["clasificacion"], source[3]["temporada_2022"]["clasificacion"])


class TestLoggedRuns(unittest.TestCase):
    def test_log_report_creates_a_run_per_horizon_variant_and_fold(self):
        import mlflow

        from denguekay.model.tracking import log_report

        report = {"experimento": "demo_v4_b3", "parametros": {}, "horizontes": mlflow_horizons(by_horizon(), 17)}
        with TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            root = Path(folder)
            uri = f"sqlite:///{(root / 'mlflow.db').as_posix()}"
            (root / "reporte.json").write_text("{}", encoding="utf-8")
            (root / "salidas").mkdir()
            run_id = log_report("prueba_v4", report, metrics_path=root / "reporte.json", output_dir=root / "salidas",
                                tracking_uri=uri, log_datasets=False)
            mlflow.set_tracking_uri(uri)
            experiment_id = mlflow.get_run(run_id).info.experiment_id
            runs = mlflow.search_runs(experiment_ids=[experiment_id], output_format="list")
            mlflow.set_tracking_uri("")
        levels = [run.data.tags.get("nivel") for run in runs]
        self.assertEqual(levels.count("variante"), 3)     # one per horizon (they used to be missing)
        self.assertEqual(levels.count("fold"), 9)         # three blocks per horizon


if __name__ == "__main__":
    unittest.main()
