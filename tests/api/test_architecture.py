"""The API only knows the tables and the Predictor port (phase 3 of docs/backend/prompt_api_v1.md).

``apps/api`` never imports the model or feature code, nor a concrete predictor: a new model is
published without touching the API.
"""

import ast
import unittest

from denguekay.config.paths import ROOT

FORBIDDEN = ("denguekay.model", "denguekay.features", "denguekay.evaluation", "denguekay.serving.predictors.",
             "xgboost", "sklearn")


def imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
            yield from (f"{node.module}.{alias.name}" for alias in node.names)


class TestApiArchitecture(unittest.TestCase):
    def test_apps_api_imports_no_model_code_nor_concrete_predictor(self):
        found = []
        for path in sorted((ROOT / "apps" / "api").rglob("*.py")):
            for name in imports(path):
                if any(name == f.rstrip(".") or name.startswith(f if f.endswith(".") else f + ".") for f in FORBIDDEN):
                    found.append(f"{path.relative_to(ROOT)}: {name}")
        self.assertEqual(found, [])

    def test_registry_imports_no_predictor_when_loaded(self):
        from denguekay.serving import predictors

        source = (ROOT / "src" / "denguekay" / "serving" / "predictors" / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("v0_compact_xgb import", source)
        self.assertTrue(all(isinstance(path, str) for path in predictors.PREDICTORS.values()))


if __name__ == "__main__":
    unittest.main()
