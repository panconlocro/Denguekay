"""Baselines of the API v1 guards (tests/test_contract_v1_guards.py), decision G1 of docs/backend/api_v1_decisiones.md.

- One schema baseline per migration published after the ADR 0001 head (0003_oe2): the SQLite
  schema, the PostgreSQL catalog and the offline PostgreSQL SQL of that revision.
- The v1 smoke test against a real uvicorn process (smoke_v1.json).

``python tests/contract_v1_support.py record`` writes only the baselines that do not exist yet
(a new migration adds its own files). It never overwrites one: a guard that fails means a
behaviour change, not a stale baseline. The OpenAPI contract (docs/backend/openapi_v1.json) is
different: an additive change raises the minor version and regenerates it on purpose.
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
BASELINE_DIR = TESTS / "fixtures" / "contract_v1"
SMOKE_V1_BASELINE = BASELINE_DIR / "smoke_v1.json"


def revisions_after_adr_0001():
    """(down_revision, revision) of each migration after 0003_oe2, oldest first."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    import equivalence_support as eq
    from denguekay.config.paths import ALEMBIC_CONFIG

    script = ScriptDirectory.from_config(Config(str(ALEMBIC_CONFIG)))
    chain = []
    for item in script.walk_revisions("base", "heads"):
        if item.revision == eq.ADR_0001_HEAD:
            break
        chain.append((item.down_revision, item.revision))
    return list(reversed(chain))


def schema_baselines(revision):
    return {"sqlite": BASELINE_DIR / f"schema_{revision}_sqlite.sql",
            "postgresql": BASELINE_DIR / f"schema_{revision}_postgresql.json",
            "offline_sql": BASELINE_DIR / f"migracion_{revision}_postgresql.sql"}


def read_text(path):
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def record():
    """Write the missing baselines; existing ones are left untouched."""
    sys.path[:0] = [str(ROOT), str(TESTS)]
    import equivalence_support as eq
    from backend_support import url_pg_pruebas

    url = url_pg_pruebas()
    if url is None:
        raise SystemExit("Define DENGUEKAY_PG_PRUEBAS_URL para registrar el esquema PostgreSQL")
    for down, revision in revisions_after_adr_0001():
        files = schema_baselines(revision)
        values = {"sqlite": lambda: eq.sqlite_schema(revision),
                  "postgresql": lambda: json.dumps(eq.postgresql_schema(url, revision), indent=1,
                                                   ensure_ascii=False) + "\n",
                  "offline_sql": lambda: eq.offline_postgresql_sql(f"{down}:{revision}")}
        for kind, path in files.items():
            if path.exists():
                print("ya existe (no se toca)", path.relative_to(ROOT))
            else:
                eq.write_new(path, values[kind]())
    if SMOKE_V1_BASELINE.exists():
        print("ya existe (no se toca)", SMOKE_V1_BASELINE.relative_to(ROOT))
    else:
        eq.write_new(SMOKE_V1_BASELINE, json.dumps(eq.smoke_results(), indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accion", choices=["record"])
    parser.parse_args()
    record()
