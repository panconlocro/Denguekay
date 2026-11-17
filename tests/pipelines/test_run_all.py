"""Order and selection of the pipeline steps (nothing is executed)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from denguekay.pipelines import run_all


class TestSteps(unittest.TestCase):
    def test_v4_steps_follow_the_numbering(self):
        steps = run_all.available_steps(version="v4")
        self.assertEqual(steps, sorted(steps))
        self.assertEqual(len(steps), 12)
        self.assertEqual(steps[0], "01_bronze_geografia")
        self.assertEqual(steps[-2:], ["11_gold", "99_verificacion"])

    def test_default_version_is_v4(self):
        self.assertEqual(run_all.available_steps(), run_all.available_steps(version="v4"))

    def test_range_by_prefix(self):
        self.assertEqual(run_all.available_steps("05", "06", version="v4"), ["05_bronze_sala", "06_silver_clima"])
        with self.assertRaises(ValueError):
            run_all.available_steps("98")

    def test_only_existing_notebooks(self):
        for step in run_all.available_steps():
            self.assertTrue((run_all.version_folder("v4") / f"{step}.ipynb").exists())

    def test_version_without_folder_fails_clearly(self):
        with self.assertRaises(FileNotFoundError):
            run_all.available_steps(version="v2")
        self.assertEqual(run_all.main(["--version", "v2", "--lista"]), 2)

    def test_no_step_runs_in_place(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(run_all.subprocess, "run") as sub:
            sub.return_value.returncode = 0
            sub.return_value.stdout = sub.return_value.stderr = ""
            run_all.run(["01_bronze_geografia"], destination=Path(temp))
        self.assertNotIn("--inplace", sub.call_args.args[0])
        self.assertIn("--output-dir", sub.call_args.args[0])

    def test_failure_prints_cell_and_error(self):
        notebook = {"cells": [{"source": ["1/0"], "outputs": [
            {"output_type": "error", "ename": "ZeroDivisionError", "evalue": "division by zero"}]}]}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "n.ipynb"
            path.write_text(json.dumps(notebook), encoding="utf-8")
            with patch("builtins.print") as printed:
                run_all._report_failure(path, "")
        shown = " ".join(str(call.args[0]) for call in printed.call_args_list)
        self.assertIn("1/0", shown)
        self.assertIn("ZeroDivisionError", shown)

    def test_checks_existing_release_without_running_notebooks(self):
        with patch.object(run_all, "run") as run, patch.object(run_all, "_verify", return_value=1) as verify:
            self.assertEqual(run_all.main(["--version", "v4", "--solo-verificar", "--desde-release"]), 1)
        run.assert_not_called()
        verify.assert_called_once_with(release=True)

    def test_published_bronze_is_restored_before_running_v4(self):
        from denguekay.pipelines import v4_inputs

        with patch.object(v4_inputs, "restore_published_bronze") as restore, patch.object(run_all, "run") as run:
            def execute(steps, **kwargs):
                restore.assert_called_once()
                self.assertEqual(steps, ["01_bronze_geografia"])
                self.assertFalse(kwargs["offline"])
                return [{"paso": steps[0], "codigo": 0, "segundos": 0}]

            run.side_effect = execute
            self.assertEqual(run_all.main(["--version", "v4", "--bronze-publicado", "--hasta", "01"]), 0)


if __name__ == "__main__":
    unittest.main()
