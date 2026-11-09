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


if __name__ == "__main__":
    unittest.main()
