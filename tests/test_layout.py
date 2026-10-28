"""Repository layout guards of the monorepo restructure (docs/decisions/0001-repo-restructure.md).

- No leftover references to the legacy ``src`` package: modules are ``denguekay.*`` and
  ``apps.*``; the only path under ``src/`` is ``src/denguekay/``.
- One-way dependencies: ``research`` may import ``denguekay``, never the reverse; the
  product (``denguekay``, ``apps`` and the pipeline notebooks) never imports ``research``,
  and ``denguekay`` never imports ``apps``.
"""

import ast
import json
import re
import subprocess
import unittest
from pathlib import Path

from denguekay.config.paths import ROOT

# Product code, its tests and the configuration that names modules or paths.
SCANNED_ROOTS = ("src/", "apps/", "tests/", "pipelines/", ".github/")
SCANNED_FILES = ("alembic.ini", ".coveragerc", "pyproject.toml", "requirements.txt", ".claude/settings.json")
LEGACY_MODULE = re.compile(r"(?<![\w.])src\.[A-Za-z_]")
LEGACY_PATH = re.compile(r"(?<![\w./])src/(?!denguekay/)")
SELF = Path(__file__).resolve().relative_to(ROOT).as_posix()


def tracked_files():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f]


def scanned_files():
    for f in tracked_files():
        if f == SELF or f.startswith("tests/fixtures/") or not (ROOT / f).exists():
            continue
        if f.startswith(SCANNED_ROOTS) or f in SCANNED_FILES:
            yield f


def text_of(path):
    raw = (ROOT / path).read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def notebook_code(path):
    nb = json.loads(text_of(path))
    cells = ("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    return "\n".join("\n".join("pass" if l.lstrip().startswith(("%", "!")) else l for l in c.split("\n"))
                     for c in cells)


def imported_roots(code, where):
    """Top-level package of every import, including importlib.import_module("...") literals."""
    roots = set()
    for node in ast.walk(ast.parse(code, where)):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".")[0])
        elif (isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", None)) == "import_module"
              and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
            roots.add(node.args[0].value.split(".")[0])
    return roots


class TestNoLegacySrc(unittest.TestCase):
    def test_no_module_or_path_of_the_legacy_src_package(self):
        hits = []
        for f in scanned_files():
            text = text_of(f)
            if text is None:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if LEGACY_MODULE.search(line) or LEGACY_PATH.search(line):
                    hits.append(f"{f}:{n}: {line.strip()[:120]}")
        self.assertEqual(hits, [])

    def test_src_only_holds_the_denguekay_package(self):
        legacy = [f for f in tracked_files() if f.startswith("src/") and not f.startswith("src/denguekay/")]
        self.assertEqual(legacy, [])


class TestOneWayDependencies(unittest.TestCase):
    def product_modules(self, prefix):
        for f in tracked_files():
            if f.startswith(prefix) and f.endswith(".py"):
                yield f, text_of(f)
            elif f.startswith(prefix) and f.endswith(".ipynb"):
                yield f, notebook_code(f)

    def assertNeverImports(self, prefix, forbidden):
        found = {}
        for f, code in self.product_modules(prefix):
            bad = imported_roots(code, f) & forbidden
            if bad:
                found[f] = sorted(bad)
        self.assertEqual(found, {})

    def test_denguekay_imports_neither_research_nor_apps(self):
        self.assertNeverImports("src/denguekay/", {"research", "apps"})

    def test_apps_never_imports_research(self):
        self.assertNeverImports("apps/", {"research"})

    def test_pipeline_notebooks_never_import_research(self):
        self.assertNeverImports("pipelines/", {"research"})

    def test_product_never_puts_research_on_sys_path(self):
        pattern = re.compile(r"sys\.path\.(insert|append)\([^)]*(research|RESEARCH)")
        found = [f for prefix in ("src/denguekay/", "apps/", "pipelines/")
                 for f, code in self.product_modules(prefix) if pattern.search(code)]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
