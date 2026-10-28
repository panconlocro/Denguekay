"""Equivalence guards of the restructure: the product must behave exactly as at the baseline.

The baseline (tests/fixtures/equivalence/) was recorded before any module moved. A guard that
fails means a behaviour change, not a stale baseline: never re-record it to make a test pass.
"""

import json
import os
from pathlib import Path
import tempfile
import unittest

import equivalence_support as eq
from backend_support import url_pg_pruebas


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@unittest.skipUnless(eq.data_available(), "requiere silver integrado, gold y epi histórico locales")
class TestFrozenPredictions(unittest.TestCase):
    """V1 and V2 reproduce their baseline predictions bit for bit (seed 17)."""

    def check(self, setup):
        measured = eq.frozen_prediction_digests_in_subprocess(setup)
        key = eq.setup_key(measured.pop("setup"))
        baseline = read_json(eq.PREDICTIONS_BASELINE)
        self.assertIn(key, baseline, f"sin línea base para {key}")
        self.assertEqual(measured, baseline[key])

    def test_cpu_two_threads(self):
        self.check(eq.CPU_SETUP)

    def test_cuda(self):
        if "device=cuda" not in read_json(eq.PREDICTIONS_BASELINE) or not eq.cuda_available():
            self.skipTest("sin GPU CUDA o sin línea base CUDA")
        self.check(eq.CUDA_SETUP)


class TestOpenAPIContract(unittest.TestCase):
    def test_contract_matches_committed_openapi(self):
        """Paths, operationIds, parameters and schemas; examples depend on the exporting DB."""
        self.assertEqual(eq.openapi_contract(), eq.strip_examples(eq.committed_openapi()))

    @unittest.skipUnless(os.environ.get("DENGUEKAY_EQ_OPENAPI_BD") == "1",
                         "exportación completa solo con DENGUEKAY_EQ_OPENAPI_BD=1 y DATABASE_URL de la BD local")
    def test_full_export_from_local_database_is_identical(self):
        """Read-only: exports with the examples of the configured DB to a temporary file."""
        from apps.api.tools import export_openapi as exportar_openapi

        original = exportar_openapi.OPENAPI_JSON
        with tempfile.TemporaryDirectory() as folder:
            exportar_openapi.OPENAPI_JSON = Path(folder) / "docs" / "backend" / "openapi.json"
            try:
                exportar_openapi.export()
                exported = exportar_openapi.OPENAPI_JSON.read_text(encoding="utf-8")
            finally:
                exportar_openapi.OPENAPI_JSON = original
        self.assertEqual(exported.replace("\r\n", "\n"), original.read_text(encoding="utf-8").replace("\r\n", "\n"))


class TestMigratedSchema(unittest.TestCase):
    def test_offline_postgresql_sql_matches_evidence(self):
        self.assertEqual(eq.offline_postgresql_sql(), eq.committed_offline_sql())

    def test_sqlite_schema_matches_baseline(self):
        self.assertEqual(eq.sqlite_schema(), eq.SQLITE_SCHEMA_BASELINE.read_text(encoding="utf-8").replace("\r\n", "\n"))

    @unittest.skipUnless(url_pg_pruebas(), "Sin DENGUEKAY_PG_PRUEBAS_URL: se omiten las pruebas en PostgreSQL")
    def test_postgresql_schema_matches_baseline(self):
        self.assertEqual(eq.postgresql_schema(url_pg_pruebas()), read_json(eq.POSTGRESQL_SCHEMA_BASELINE))


class TestUvicornSmoke(unittest.TestCase):
    def test_uvicorn_serves_and_smoke_test_matches_baseline(self):
        self.assertEqual(eq.smoke_results(), read_json(eq.SMOKE_BASELINE))


if __name__ == "__main__":
    unittest.main()
