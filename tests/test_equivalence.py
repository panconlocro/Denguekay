"""Equivalence guards of the restructure: the product must behave exactly as at the baseline.

The baseline (tests/fixtures/equivalence/) was recorded before any module moved. A guard that
fails means a behaviour change, not a stale baseline: never re-record it to make a test pass.

API v1 (decision G1 of docs/backend/api_v1_decisiones.md, approved by Rosa on 29/10/2026): the
OpenAPI guard is replaced by the v1 contract guard (tests/test_contract_v1_guards.py), the schema
guards check the ADR 0001 head 0003_oe2, and the ADR 0001 smoke test (smoke.json, 15 routes) no
longer runs: it is history, reproducible from the tag restructure-done.
"""

import json
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


class TestMigratedSchema(unittest.TestCase):
    """The schema at the ADR 0001 head (0003_oe2) is the baseline; published migrations never change."""

    def test_offline_postgresql_sql_matches_evidence(self):
        self.assertEqual(eq.offline_postgresql_sql(), eq.committed_offline_sql())

    def test_sqlite_schema_matches_baseline(self):
        self.assertEqual(eq.sqlite_schema(), eq.SQLITE_SCHEMA_BASELINE.read_text(encoding="utf-8").replace("\r\n", "\n"))

    @unittest.skipUnless(url_pg_pruebas(), "Sin DENGUEKAY_PG_PRUEBAS_URL: se omiten las pruebas en PostgreSQL")
    def test_postgresql_schema_matches_baseline(self):
        self.assertEqual(eq.postgresql_schema(url_pg_pruebas()), read_json(eq.POSTGRESQL_SCHEMA_BASELINE))


if __name__ == "__main__":
    unittest.main()
