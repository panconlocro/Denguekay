"""Workflows of the weekly update and of the monthly drift review (HU0019-1 and HU0009-2).

They only read the YAML: the behaviour of ``v4_weekly`` and ``drift`` is proved by their own tests. What is checked
here is what the files promise: the schedule, the commands, the minimum permissions and that, without secrets, the
jobs end with a notice instead of failing."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

from denguekay.config.paths import ROOT

WORKFLOWS = ROOT / ".github" / "workflows"
SECRETS_STEP = "secretos"
CONFIGURED = "steps.secretos.outputs.configurados == 'true'"


def load(name):
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def triggers(workflow):
    return workflow.get("on", workflow.get(True))   # YAML 1.1 reads the key ``on`` as True


def steps_of(workflow):
    (job,) = workflow["jobs"].values()
    return job["steps"]


def commands(workflow):
    return "\n".join(step.get("run", "") for step in steps_of(workflow))


class TestWeekly(unittest.TestCase):
    def setUp(self):
        self.workflow = load("weekly_v4.yml")

    def test_it_runs_monday_and_thursday_at_7_in_lima_and_by_hand(self):
        schedule = triggers(self.workflow)["schedule"]
        self.assertEqual([item["cron"] for item in schedule], ["0 12 * * 1,4"])   # 12:00 UTC = 07:00 Lima (UTC-5)
        self.assertIn("workflow_dispatch", triggers(self.workflow))

    def test_it_fetches_the_frozen_inputs_verified_and_runs_the_weekly_update(self):
        text = commands(self.workflow)
        self.assertIn("python -m denguekay.data.ingestion.release_bundles --version v4 --solo datos_v4.zip modelo_v4.zip",
                      text)
        self.assertIn("python -m denguekay.pipelines.v4_weekly $banderas", text)
        self.assertIn('banderas="--preparar"', text)   # an empty runner restores what it lacks, it never publishes
        self.assertNotIn("--inicial", text)
        self.assertLess(text.index("release_bundles"), text.index("v4_weekly"))

    def test_the_dry_run_input_exists_and_defaults_to_false(self):
        dispatch = triggers(self.workflow)["workflow_dispatch"]["inputs"]["dry_run"]
        self.assertEqual((dispatch["type"], dispatch["default"]), ("boolean", False))
        self.assertIn("--dry-run", commands(self.workflow))

    def test_the_archive_of_emissions_is_kept_as_an_artifact_and_the_bronze_is_cached(self):
        by_uses = {step["uses"].split("@")[0]: step for step in steps_of(self.workflow) if "uses" in step}
        upload = by_uses["actions/upload-artifact"]
        self.assertIn("models/serving/actualizacion_semanal/emisiones", upload["with"]["path"])
        self.assertEqual(upload["with"]["retention-days"], 90)
        self.assertEqual(by_uses["actions/cache"]["with"]["path"], "data/bronze")

    def test_the_job_has_the_environment_of_the_service_and_no_secret_outside_env(self):
        (job,) = self.workflow["jobs"].values()
        self.assertEqual(job["env"]["STORAGE_BACKEND"], "supabase")
        for name in ("DATABASE_URL", "SUPABASE_URL", "SUPABASE_SECRET_KEY"):
            self.assertEqual(job["env"][name], "${{ secrets.%s }}" % name)
        self.assertNotIn("secrets.", commands(self.workflow))


class TestDrift(unittest.TestCase):
    def setUp(self):
        self.workflow = load("drift_monthly.yml")

    def test_it_runs_monthly_at_7_in_lima_and_by_hand(self):
        self.assertEqual([item["cron"] for item in triggers(self.workflow)["schedule"]], ["0 12 1 * *"])
        self.assertIn("workflow_dispatch", triggers(self.workflow))

    def test_it_runs_the_drift_review_against_the_same_database(self):
        self.assertIn("python -m denguekay.serving.drift", commands(self.workflow))
        (job,) = self.workflow["jobs"].values()
        self.assertEqual(job["env"]["DATABASE_URL"], "${{ secrets.DATABASE_URL }}")
        self.assertEqual(load("weekly_v4.yml")["jobs"]["actualizar"]["env"]["DATABASE_URL"], job["env"]["DATABASE_URL"])
        self.assertNotIn("secrets.", commands(self.workflow))


class TestCommon(unittest.TestCase):
    NAMES = ("weekly_v4.yml", "drift_monthly.yml")

    def test_the_permissions_are_the_minimum(self):
        for name in self.NAMES:
            workflow = load(name)
            with self.subTest(name=name):
                self.assertEqual(workflow["permissions"], {"contents": "read"})
                for job in workflow["jobs"].values():
                    self.assertNotIn("permissions", job)   # no job asks for more than the workflow

    def test_checkout_keeps_no_credentials_and_runs_are_never_cancelled_half_way(self):
        for name in self.NAMES:
            workflow = load(name)
            with self.subTest(name=name):
                checkout = next(s for s in steps_of(workflow) if s.get("uses", "").startswith("actions/checkout"))
                self.assertIs(checkout["with"]["persist-credentials"], False)
                self.assertIs(workflow["concurrency"]["cancel-in-progress"], False)

    def test_without_the_secrets_every_step_after_the_check_is_skipped(self):
        for name in self.NAMES:
            steps = steps_of(load(name))
            with self.subTest(name=name):
                self.assertEqual(steps[0]["id"], SECRETS_STEP)
                for step in steps[1:]:
                    self.assertIn(CONFIGURED, step["if"], step.get("name") or step.get("uses"))

    def test_the_check_step_ends_with_a_notice_and_exit_0_without_secrets_and_flags_them_with_them(self):
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("no hay bash para ejecutar el paso de comprobación")
        for name, variables in (("weekly_v4.yml", ("DATABASE_URL", "SUPABASE_URL", "SUPABASE_SECRET_KEY")),
                                ("drift_monthly.yml", ("DATABASE_URL",))):
            script = steps_of(load(name))[0]["run"]
            for configured in (False, True):
                with self.subTest(name=name, configured=configured), tempfile.TemporaryDirectory() as folder:
                    output, summary = Path(folder) / "salida", Path(folder) / "resumen"
                    env = {key: value for key, value in os.environ.items() if key not in variables}
                    env.update({"GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(summary)})
                    env.update({variable: "x" for variable in variables} if configured else {})
                    done = subprocess.run([bash, "-c", script], env=env, capture_output=True, text=True, timeout=60)
                    self.assertEqual(done.returncode, 0, done.stderr)
                    self.assertEqual(output.read_text().strip(), f"configurados={'true' if configured else 'false'}")
                    if configured:
                        self.assertFalse(summary.exists())
                    else:
                        self.assertIn("::notice::", done.stdout)
                        self.assertIn("OMITID", summary.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
