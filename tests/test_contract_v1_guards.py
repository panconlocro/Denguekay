"""Guards of the API v1 contract (decision G1 of docs/backend/api_v1_decisiones.md).

- The generated OpenAPI equals docs/backend/openapi_v1.json (semver rules in the failure message).
- Each migration after the ADR 0001 head has a schema baseline that never changes.
- The v1 smoke test against uvicorn matches tests/fixtures/contract_v1/smoke_v1.json.

The schema and smoke baselines are recorded once with ``python tests/contract_v1_support.py record``
and are never re-recorded to make a test pass.
"""

import json
import re
import unittest

import contract_v1_support as v1
import equivalence_support as eq
from backend_support import url_pg_pruebas
from apps.api.contract import CONTRACT_VERSION
from denguekay.config.paths import OPENAPI_JSON, OPENAPI_V1_JSON

SEMVER_MESSAGE = """El contrato OpenAPI generado difiere de docs/backend/openapi_v1.json.
- Cambio aditivo (ruta, campo opcional o valor nuevo): sube la versión minor en apps/api/contract.py
  (CONTRACT_VERSION), anótalo en el changelog de docs/backend/contrato_api.md y regenera a propósito con
  `.\\.venv\\Scripts\\python -m apps.api.tools.export_openapi --contrato`.
- Cambio que rompe (renombrar o quitar un campo o una ruta, cambiar un tipo, volver obligatorio un campo):
  no se permite en /api/v1; va en /api/v2 con `feat(api)!`.
Diferencias: {differences}"""


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def differences(generated, committed):
    """Short list of the paths and schemas that were added, removed or changed."""
    found = []
    for section, a, b in (("ruta", generated["paths"], committed["paths"]),
                          ("esquema", generated["components"]["schemas"], committed["components"]["schemas"])):
        found += [f"{section} nueva {k}" for k in sorted(set(a) - set(b))]
        found += [f"{section} quitada {k}" for k in sorted(set(b) - set(a))]
        found += [f"{section} cambiada {k}" for k in sorted(set(a) & set(b)) if a[k] != b[k]]
    if generated.get("info") != committed.get("info"):
        found.append("info cambiada")
    return "; ".join(found) or "fuera de rutas y esquemas"


class TestOpenAPIContractV1(unittest.TestCase):
    def test_generated_contract_matches_openapi_v1(self):
        generated, committed = eq.openapi_contract(), read_json(OPENAPI_V1_JSON)
        if generated != committed:
            self.fail(SEMVER_MESSAGE.format(differences=differences(generated, committed)))

    def test_published_openapi_has_the_same_contract(self):
        """openapi.json only adds examples from a real database to openapi_v1.json."""
        self.assertEqual(eq.strip_examples(read_json(OPENAPI_JSON)), read_json(OPENAPI_V1_JSON))

    def test_contract_version_is_v1_semver(self):
        self.assertRegex(CONTRACT_VERSION, r"^1\.\d+\.\d+$")
        self.assertEqual(read_json(OPENAPI_V1_JSON)["info"]["version"], CONTRACT_VERSION)
        self.assertTrue(all(re.match(r"^/api/v1/", p) for p in read_json(OPENAPI_V1_JSON)["paths"]))


class TestSchemaPerMigration(unittest.TestCase):
    """Schema baseline of each migration after 0003_oe2; published migrations never change."""

    def setUp(self):
        self.revisions = v1.revisions_after_adr_0001()

    def test_every_new_migration_has_its_baselines(self):
        self.assertTrue(self.revisions, "se esperaba al menos la migración 0004_v1")
        for _, revision in self.revisions:
            for kind, path in v1.schema_baselines(revision).items():
                with self.subTest(revision=revision, baseline=kind):
                    self.assertTrue(path.is_file(), f"Falta {path.name}: python tests/contract_v1_support.py record")

    def test_sqlite_schema_matches_baseline(self):
        for _, revision in self.revisions:
            with self.subTest(revision=revision):
                self.assertEqual(eq.sqlite_schema(revision), v1.read_text(v1.schema_baselines(revision)["sqlite"]))

    def test_offline_postgresql_sql_matches_baseline(self):
        for down, revision in self.revisions:
            with self.subTest(revision=revision):
                self.assertEqual(eq.offline_postgresql_sql(f"{down}:{revision}"),
                                 v1.read_text(v1.schema_baselines(revision)["offline_sql"]))

    @unittest.skipUnless(url_pg_pruebas(), "Sin DENGUEKAY_PG_PRUEBAS_URL: se omiten las pruebas en PostgreSQL")
    def test_postgresql_schema_matches_baseline(self):
        for _, revision in self.revisions:
            with self.subTest(revision=revision):
                self.assertEqual(eq.postgresql_schema(url_pg_pruebas(), revision),
                                 read_json(v1.schema_baselines(revision)["postgresql"]))


class TestUvicornSmokeV1(unittest.TestCase):
    def test_uvicorn_serves_and_smoke_test_matches_v1_baseline(self):
        self.assertEqual(eq.smoke_results(), read_json(v1.SMOKE_V1_BASELINE))


if __name__ == "__main__":
    unittest.main()
