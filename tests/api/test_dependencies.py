"""The API runs with requirements-api.txt: it never imports the research or pipeline-only dependencies."""

import json
import subprocess
import sys
import unittest

from denguekay.config.paths import ROOT

FORBIDDEN = ("mlflow", "great_expectations", "optuna", "matplotlib", "geopandas")
# What the API loads at run time: the application and, on the first inference, the registered predictors.
RUNTIME_MODULES = ("apps.api.main", "denguekay.serving.inference", "denguekay.serving.predictors.v0_compact_xgb",
                   "denguekay.serving.predictors.v2_e3_s4")


def requirement_lines(name):
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def imported_after(modules):
    """Top-level packages loaded in a clean interpreter after importing ``modules``."""
    code = ("import json, sys\n"
            f"for name in {list(modules)!r}:\n"
            "    __import__(name)\n"
            "print(json.dumps(sorted({m.split('.')[0] for m in sys.modules})))\n")
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise AssertionError(result.stderr)
    return set(json.loads(result.stdout.strip().splitlines()[-1]))


class TestDependenciasDeLaAPI(unittest.TestCase):
    def test_importar_la_api_no_importa_dependencias_pesadas(self):
        loaded = imported_after(("apps.api.main",))
        self.assertEqual(sorted(loaded.intersection(FORBIDDEN)), [])
        for name in ("xgboost", "sklearn", "scipy"):  # the predictors are imported only when used
            self.assertNotIn(name, loaded)

    def test_inferir_con_los_predictores_registrados_tampoco(self):
        self.assertEqual(sorted(imported_after(RUNTIME_MODULES).intersection(FORBIDDEN)), [])

    def test_requirements_api_es_un_subconjunto_de_requirements(self):
        api = requirement_lines("requirements-api.txt")
        self.assertTrue(api)
        self.assertEqual([line for line in api if line not in requirement_lines("requirements.txt")], [])
        names = {line.split("[")[0].split(">")[0].split("<")[0].split("=")[0].strip().lower() for line in api}
        self.assertEqual(sorted(names.intersection({*FORBIDDEN, "great-expectations"})), [])


if __name__ == "__main__":
    unittest.main()
