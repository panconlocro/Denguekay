"""The traceability table of the user stories (docs/backend/trazabilidad_hu.md) cites real files and real tests.

The source document of the criteria is not in the repository, so the list of scenarios is written here: the 76 scenarios
of ``US_Criterios_De_Aceptacion_Final.xlsm`` (17/11/2026). A scenario without a row, a row without a state or a test that
no longer exists makes this test fail."""

import re
import subprocess
import unittest

from denguekay.config.paths import ROOT

TABLE = ROOT / "docs" / "backend" / "trazabilidad_hu.md"
SCENARIOS = (
    "HU0001-1 HU0001-2 HU0001-3 HU0001-4 HU0002-1 HU0002-2 HU0002-3 HU0002-4 HU0003-1 HU0003-2 HU0003-3 HU0003-4 "
    "HU0004-1 HU0004-2 HU0004-3 HU0004-4 HU0004-5 HU0005-1 HU0005-2 HU0005-3 HU0005-4 HU0005-5 HU0006-1 HU0006-2 "
    "HU0006-3 HU0007-1 HU0007-2 HU0007-3 HU0007-4 HU0007-5 HU0008-1 HU0008-2 HU0008-3 HU0008-4 HU0009-1 HU0009-2 "
    "HU0009-3 HU0009-4 HU0010-1 HU0010-2 HU0010-3 HU0010-4 HU0011-1 HU0011-2 HU0011-3 HU0012-1 HU0012-2 HU0012-3 "
    "HU0012-4 HU0013-1 HU0013-2 HU0013-3 HU0014-1 HU0014-2 HU0014-3 HU0014-4 HU0015-1 HU0015-2 HU0015-3 HU0015-4 "
    "HU0016-1 HU0016-2 HU0016-3 HU0016-4 HU0017-1 HU0017-2 HU0017-3 HU0018-1 HU0018-2 HU0018-3 HU0018-4 HU0019-1 "
    "HU0019-2 HU0019-3 HU0019-4 HU0019-5").split()
RETIRED = {"HU0002-3", "HU0010-3", "HU0011-2"}
RETROSPECTIVE = {"HU0007-4"}
# Met in the code and its tests, but the V4 versions in production only carry the importances and the temporal
# partition once the V4 is republished (docs/backend/trazabilidad_hu.md, «Fuente y estados»).
AWAITING_REPUBLICATION = {"HU0008-3", "HU0008-4"}
REPUBLICATION_NOTE = " (efectivo en producción tras republicar la V4)"
STATES = ("cumplido", "cumplido retrospectivo", "retirado")
ROOTS = (ROOT, ROOT / "src" / "denguekay", ROOT / "docs" / "backend", ROOT / "docs", ROOT / "apps" / "web",
         ROOT / "apps")
EXTENSIONS = (".py", ".yml", ".md", ".json", ".ps1", ".mjs", ".ts", ".yaml")


def rows():
    """{scenario: [cells]} of every table row that starts with a scenario id."""
    found = {}
    for line in TABLE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\|\s*(HU\d{4}-\d+)\b", line)
        if match:
            found[match.group(1)] = [cell.strip() for cell in line.strip().strip("|").split(" | ")]
    return found


def test_names_in_the_tree():
    names = set()
    for base in (ROOT / "tests", ROOT / "research"):
        for path in base.rglob("test_*.py"):
            names.update(re.findall(r"def (test_\w+)", path.read_text(encoding="utf-8")))
    return names


class TestTraceabilityTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = rows()
        try:   # a cited file must be in Git: ``data/`` and other ignored folders do not exist in the CI
            listing = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
            cls.tracked = {ROOT / line for line in listing.stdout.splitlines()}
        except (OSError, subprocess.CalledProcessError):
            cls.tracked = None

    @classmethod
    def versioned(cls, path):
        return path.is_file() and (cls.tracked is None or path in cls.tracked)

    def test_there_is_one_row_per_scenario_and_nothing_else(self):
        self.assertEqual(sorted(self.rows), sorted(SCENARIOS))
        self.assertEqual(len(SCENARIOS), 76)

    def test_every_row_has_module_test_and_one_of_the_three_states(self):
        for scenario, cells in self.rows.items():
            with self.subTest(scenario=scenario):
                self.assertEqual(len(cells), 4, cells)
                state = cells[3]
                self.assertTrue(state.startswith(STATES), state)
                if scenario in RETIRED:
                    self.assertTrue(state.startswith("retirado") and len(state) > 40, "falta el motivo del retiro")
                elif scenario in RETROSPECTIVE:
                    self.assertTrue(state.startswith("cumplido retrospectivo"))
                    for reserve in ("2022–2024", "una semilla", "después de ver los resultados"):
                        self.assertIn(reserve, state)
                else:
                    expected = "cumplido" + (REPUBLICATION_NOTE if scenario in AWAITING_REPUBLICATION else "")
                    self.assertEqual(state, expected)
                    self.assertTrue(cells[1] and cells[2] and "—" != cells[2])

    def test_no_state_depends_on_the_operation_or_on_the_oe4(self):
        text = TABLE.read_text(encoding="utf-8")
        for word in ("se cumple en el OE4", "por verificar"):
            self.assertNotIn(word, text)
        states = {cells[3].replace(REPUBLICATION_NOTE, "").split(":")[0].split(" el ")[0]
                  for cells in self.rows.values()}
        self.assertTrue(states <= {"cumplido", "cumplido retrospectivo", "retirado"}, states)

    def test_every_cited_file_exists_and_every_cited_test_is_defined(self):
        defined = test_names_in_the_tree()
        for scenario, cells in self.rows.items():
            for token in re.findall(r"`([^`]+)`", " ".join(cells[1:3])):
                token = token.split(" ")[0]
                with self.subTest(scenario=scenario, token=token):
                    if token.startswith("test_"):
                        self.assertIn(token, defined)
                    elif "/" in token and token.endswith(EXTENSIONS):
                        self.assertTrue(any(self.versioned(base / token) for base in ROOTS),
                                        f"no existe o no está versionado: {token}")

    def test_the_hu0009_3_rows_name_the_refit_tests_that_the_plan_asks_for(self):
        cells = " ".join(self.rows["HU0009-3"])
        for needed in ("model/refit_v4.py", "tests/model/test_refit_v4.py",
                       "test_a_refit_package_moves_the_labels_cutoff_and_switches_the_notice_off",
                       "test_a_refit_package_is_served_through_paquete_dir_without_the_release_manifest"):
            self.assertIn(needed, cells)


if __name__ == "__main__":
    unittest.main()
