"""Order and selection of the pipeline steps (nothing is executed)."""

import unittest

from denguekay.pipelines import run_all


class TestSteps(unittest.TestCase):
    def test_order_follows_the_numbering(self):
        self.assertEqual(run_all.STEPS, sorted(run_all.STEPS))
        self.assertEqual(run_all.STEPS[-1], "10_silver_to_gold")

    def test_range_by_prefix(self):
        steps = run_all.available_steps("06", "07")
        self.assertEqual(steps[0], "06_ingesta_epi")
        self.assertIn("06b_ingesta_sala", steps)
        self.assertEqual(steps[-1], "07_bronze_to_silver_epi")
        with self.assertRaises(ValueError):
            run_all.available_steps("99")

    def test_only_existing_notebooks(self):
        for step in run_all.available_steps():
            self.assertTrue((run_all.NOTEBOOKS / f"{step}.ipynb").exists())

    def test_v4_has_separate_merge_and_gold_steps(self):
        v4 = run_all.available_steps(version="v4")
        self.assertEqual(v4[-2:], ["09b_integrado_confirmados_v4", "11_silver_to_gold_v4"])
        self.assertFalse({"02_ingesta_meteo", "09_silver_merge_epi", "10_silver_to_gold"}.intersection(v4))
        self.assertEqual(run_all.available_steps("06c", "07b", version="v4"),
                         ["06c_sala_confirmados_v4", "07b_historico_confirmados_v4"])


if __name__ == "__main__":
    unittest.main()
