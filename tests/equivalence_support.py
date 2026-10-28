"""Measurements behind the restructure equivalence guards (tests/test_equivalence.py).

Each function returns a value that must stay identical while the repository is restructured:
frozen-model predictions, the API contract, the migrated schema and the smoke test against a
real uvicorn process. ``python tests/equivalence_support.py record`` wrote the baseline in
``tests/fixtures/equivalence/`` once, before any module moved; it refuses to overwrite it.
"""

import argparse
from contextlib import closing, contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
BASELINE_DIR = TESTS / "fixtures" / "equivalence"
PREDICTIONS_BASELINE = BASELINE_DIR / "predictions.json"
SQLITE_SCHEMA_BASELINE = BASELINE_DIR / "schema_sqlite.sql"
POSTGRESQL_SCHEMA_BASELINE = BASELINE_DIR / "schema_postgresql.json"
SMOKE_BASELINE = BASELINE_DIR / "smoke.json"

SMOKE_API_KEY = "clave-local-de-equivalencia"
PREDICTION_KEY = ["ubigeo", "semana_inicio", "horizonte", "bloque"]
PREDICTION_VALUES = ["casos_predichos", "probabilidad_brote"]
# XGBoost is deterministic for a fixed device and thread count, but CPU and CUDA (and different
# n_jobs on CPU) produce different bits, so each baseline is keyed by the training setup.
CPU_SETUP = {"DENGUEKAY_XGB_DEVICE": "cpu", "DENGUEKAY_XGB_NJOBS": "2"}
CUDA_SETUP = {"DENGUEKAY_XGB_DEVICE": "cuda"}


def subprocess_env(**extra):
    """Environment for child processes: repo root and tests/ importable, no real DB or key."""
    env = {**os.environ, "DATABASE_URL": "", "API_KEY": "", "MPLBACKEND": "Agg", **extra}
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(TESTS), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    return env


# --- frozen configurations (V1 and V2) -------------------------------------------------------

def data_available():
    from denguekay.config.paths import GOLD_MANIFEST, SILVER_EPI_HISTORICO, SILVER_INTEGRADO

    return SILVER_INTEGRADO.exists() and GOLD_MANIFEST.exists() and SILVER_EPI_HISTORICO.exists()


def prediction_digest(predictions):
    """SHA-256 of the predicted values in canonical key order (exact float64 bytes)."""
    import numpy as np

    ordered = predictions.sort_values(PREDICTION_KEY, kind="mergesort").reset_index(drop=True)
    digest = hashlib.sha256()
    # Column by column: the predictions carry DataFrames in ``attrs``, which frame-level astype rejects.
    keys = [ordered[c].astype(str).tolist() for c in PREDICTION_KEY]
    digest.update("|".join(",".join(row) for row in zip(*keys)).encode("utf-8"))
    for column in PREDICTION_VALUES:
        digest.update(np.ascontiguousarray(ordered[column].to_numpy(dtype="float64")).tobytes())
    return digest.hexdigest()


def frozen_prediction_digests():
    """V1 and V2 predictions with the deployment seed, computed in memory (needs local data)."""
    from src.eda.carga import cargar_integrado
    from src.modeling import configuracion_final as cf
    from src.modeling import fe_hiperparametros as fh
    from src.modeling.dispositivo import configuracion_xgboost
    from denguekay.config.paths import GOLD_MANIFEST, SILVER_INTEGRADO

    panel = cargar_integrado(SILVER_INTEGRADO)
    rule = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
    inputs = fh.insumos(panel, rule)
    result = {"setup": configuracion_xgboost()}
    for name, configuration in (("V1", cf.CONFIGURACION_2026_V1), ("V2", cf.CONFIGURACION_2026)):
        origins = cf.origenes(panel, inputs, rule, configuracion=configuration)
        predictions = cf.predecir(inputs["matrices"], origins, configuracion=configuration)
        result[name] = {"rows": len(predictions), "sha256": prediction_digest(predictions)}
    return result


def frozen_prediction_digests_in_subprocess(setup):
    """Runs in a fresh process: the XGBoost device choice is cached per process."""
    code = "import json, equivalence_support as e; print(json.dumps(e.frozen_prediction_digests()))"
    process = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=subprocess_env(**setup),
                             capture_output=True, text=True, timeout=1800)
    if process.returncode != 0:
        raise RuntimeError(process.stderr[-4000:])
    return json.loads(process.stdout.strip().splitlines()[-1])


def setup_key(setup):
    return f"device={setup['device']},n_jobs={setup['n_jobs']}" if setup["device"] == "cpu" else "device=cuda"


def cuda_available():
    from src.modeling.dispositivo import cuda_disponible

    return cuda_disponible()


# --- API contract ----------------------------------------------------------------------------

def strip_examples(value):
    """OpenAPI without ``examples``: those come from the rows of the exporting database."""
    if isinstance(value, dict):
        return {k: strip_examples(v) for k, v in value.items() if k not in ("examples", "example")}
    if isinstance(value, list):
        return [strip_examples(v) for v in value]
    return value


def openapi_contract():
    """Schema of the app built without a database, as the API serves it."""
    from src.api.main import crear_app
    from src.api.openapi import especificacion

    return strip_examples(especificacion(crear_app()))


def committed_openapi():
    from denguekay.config.paths import OPENAPI_JSON

    return json.loads(OPENAPI_JSON.read_text(encoding="utf-8"))


# --- schema after ``alembic upgrade head`` ---------------------------------------------------

def offline_postgresql_sql():
    """``alembic upgrade 0002_serving:head --sql`` for PostgreSQL, without a connection."""
    from src.db.exportar_sql_migracion import exportar

    with tempfile.TemporaryDirectory() as folder:
        return exportar(Path(folder) / "offline.sql").read_text(encoding="utf-8").replace("\r\n", "\n")


def committed_offline_sql():
    from denguekay.config.paths import MIGRACION_OE2_SQL

    return MIGRACION_OE2_SQL.read_text(encoding="utf-8").replace("\r\n", "\n")


def sqlite_schema():
    """``sqlite_master`` of an empty SQLite database migrated to head, in a stable order."""
    from sqlalchemy import text
    from sqlalchemy.engine import URL

    from backend_soporte import migrar
    from src.db.sesion import crear_motor

    with tempfile.TemporaryDirectory() as folder:
        engine = crear_motor(URL.create("sqlite", database=str(Path(folder) / "schema.db")))
        try:
            migrar(engine)
            with engine.connect() as connection:
                rows = connection.execute(text(
                    "SELECT type, name, tbl_name, sql FROM sqlite_master "
                    "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name")).all()
                version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        finally:
            engine.dispose()
    blocks = [f"-- {kind} {name} ON {table}\n{sql};" for kind, name, table, sql in rows if sql]
    return f"-- alembic_version: {version}\n" + "\n\n".join(blocks) + "\n"


POSTGRESQL_CATALOG = {
    "alembic_version": "SELECT version_num FROM alembic_version",
    "columns": """
        SELECT table_name, column_name, ordinal_position, data_type, udt_name, is_nullable, column_default,
               is_identity, identity_generation, character_maximum_length, numeric_precision, numeric_scale
        FROM information_schema.columns WHERE table_schema = 'public' ORDER BY table_name, ordinal_position""",
    "constraints": """
        SELECT conrelid::regclass::text, conname, contype, pg_get_constraintdef(oid)
        FROM pg_constraint WHERE connamespace = 'public'::regnamespace ORDER BY 1, 2""",
    "indexes": "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY 1, 2",
    "enums": """
        SELECT t.typname, e.enumsortorder, e.enumlabel FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid
        WHERE t.typnamespace = 'public'::regnamespace ORDER BY 1, 2""",
    "row_security": """
        SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class
        WHERE relnamespace = 'public'::regnamespace AND relkind = 'r' ORDER BY 1""",
    "policies": """
        SELECT tablename, policyname, permissive, roles::text, cmd, qual, with_check
        FROM pg_policies WHERE schemaname = 'public' ORDER BY 1, 2""",
    # The owner (the test user) differs between machines; grants to other roles do not.
    "grants": """
        SELECT table_name, grantee, privilege_type FROM information_schema.role_table_grants
        WHERE table_schema = 'public' AND grantee <> current_user ORDER BY 1, 2, 3""",
    "functions": """
        SELECT p.proname, pg_get_functiondef(p.oid) FROM pg_proc p
        WHERE p.pronamespace = 'public'::regnamespace ORDER BY 1, 2""",
    "triggers": """
        SELECT tgrelid::regclass::text, tgname, pg_get_triggerdef(oid) FROM pg_trigger
        WHERE NOT tgisinternal AND tgrelid::regclass::text NOT LIKE 'pg_%' ORDER BY 1, 2""",
    "comments": """
        SELECT c.relname, a.attname, col_description(c.oid, a.attnum) FROM pg_class c
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
        WHERE c.relnamespace = 'public'::regnamespace AND col_description(c.oid, a.attnum) IS NOT NULL
        UNION ALL
        SELECT c.relname, NULL, obj_description(c.oid, 'pg_class') FROM pg_class c
        WHERE c.relnamespace = 'public'::regnamespace AND obj_description(c.oid, 'pg_class') IS NOT NULL
        ORDER BY 1, 2""",
}


def postgresql_schema(url):
    """Catalog of the disposable PostgreSQL database migrated from base to head; leaves it at base."""
    from sqlalchemy import text

    from backend_soporte import migrar
    from src.db.sesion import crear_motor

    engine = crear_motor(url)
    try:
        migrar(engine, "base")
        migrar(engine)
        with engine.connect() as connection:
            catalog = {name: [[None if v is None else str(v) for v in row] for row in connection.execute(text(sql))]
                       for name, sql in POSTGRESQL_CATALOG.items()}
        migrar(engine, "base")
    finally:
        engine.dispose()
    return catalog


# --- uvicorn and smoke test ------------------------------------------------------------------

def free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def build_smoke_database(folder):
    """SQLite migrated to head with the backend fixtures published (versions, OOS, current inference)."""
    from sqlalchemy.engine import URL

    from backend_soporte import datos_muestra, motor_temporal
    from serving_soporte import preparar_muestra
    from src.db.sesion import transaccion
    from src.serving.almacenamiento import AlmacenamientoLocal
    from src.serving.cargar_datos import persistir_carga
    from src.serving.publicar import publicar_en_bd

    cfg, protocol, prepared = preparar_muestra()
    data = datos_muestra(folder, cfg.seleccion_experimental)
    data = replace(data, observaciones=[o for o in data.observaciones if o["id_semana"] >= 202530])
    storage = folder / "storage"
    engine = motor_temporal(folder)
    try:
        with transaccion(engine) as session:
            persistir_carga(session, data)
        publicar_en_bd(engine, data, protocol, prepared, (2, 4), cfg, "run-equivalencia", "huella-equivalencia",
                       AlmacenamientoLocal(storage), 0)
    finally:
        engine.dispose()
    return str(URL.create("sqlite", database=str(folder / "pruebas.db"))), storage


def create_smoke_app():
    """uvicorn ``--factory`` target: the real app with the smoke database's artifact storage."""
    from src.api.main import crear_app
    from src.serving.almacenamiento import AlmacenamientoLocal

    return crear_app(almacenamiento=AlmacenamientoLocal(os.environ["DENGUEKAY_EQ_STORAGE"]))


@contextmanager
def uvicorn_server(target, env, factory=False):
    """Starts ``python -m uvicorn <target>`` and waits until it answers; stops it afterwards."""
    import httpx

    port = free_port()
    command = [sys.executable, "-m", "uvicorn", target, "--host", "127.0.0.1", "--port", str(port)]
    if factory:
        command.append("--factory")
    log = tempfile.TemporaryFile()
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 90
        while True:
            if process.poll() is not None:
                log.seek(0)
                raise RuntimeError(f"uvicorn terminó con código {process.returncode}:\n{log.read().decode(errors='replace')[-4000:]}")
            try:
                httpx.get(url + "/openapi.json", timeout=2)
                break
            except httpx.TransportError:
                if time.monotonic() > deadline:
                    raise RuntimeError("uvicorn no respondió en 90 s")
                time.sleep(0.5)
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        log.close()


def smoke_results():
    """Status codes of ``prueba_humo`` against uvicorn, plus the module entry point ``src.api.main:app``."""
    import httpx

    from src.api.prueba_humo import ejecutar

    with tempfile.TemporaryDirectory() as name:
        folder = Path(name)
        url, storage = build_smoke_database(folder)
        env = subprocess_env(DATABASE_URL=url, API_KEY=SMOKE_API_KEY, DENGUEKAY_EQ_STORAGE=str(storage), **CPU_SETUP)
        with uvicorn_server("equivalence_support:create_smoke_app", env, factory=True) as base:
            with httpx.Client(base_url=base, timeout=120) as client:
                calls = [[r["metodo"], r["ruta"], r["http"]] for r in ejecutar(client, SMOKE_API_KEY)]
        with uvicorn_server("src.api.main:app", env) as base:
            entry_point = {"salud": httpx.get(base + "/api/v1/salud", timeout=30).status_code,
                           "rutas_openapi": len(httpx.get(base + "/openapi.json", timeout=30).json()["paths"])}
    return {"prueba_humo": calls, "entrada_modulo": entry_point}


# --- baseline --------------------------------------------------------------------------------

def write_new(path, text):
    if path.exists():
        raise SystemExit(f"{path.relative_to(ROOT)} ya existe: la línea base no se sobrescribe")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print("escrito", path.relative_to(ROOT))


def record():
    """Writes the baseline once, from the code as it is before the restructure."""
    sys.path[:0] = [str(ROOT), str(TESTS)]
    from backend_soporte import url_pg_pruebas

    predictions = {}
    setups = [CPU_SETUP] + ([CUDA_SETUP] if cuda_available() else [])
    for setup in setups:
        measured = frozen_prediction_digests_in_subprocess(setup)
        predictions[setup_key(measured.pop("setup"))] = measured
    write_new(PREDICTIONS_BASELINE, json.dumps(predictions, indent=2) + "\n")
    write_new(SQLITE_SCHEMA_BASELINE, sqlite_schema())
    url = url_pg_pruebas()
    if url is None:
        raise SystemExit("Define DENGUEKAY_PG_PRUEBAS_URL para registrar el esquema PostgreSQL")
    write_new(POSTGRESQL_SCHEMA_BASELINE, json.dumps(postgresql_schema(url), indent=1, ensure_ascii=False) + "\n")
    write_new(SMOKE_BASELINE, json.dumps(smoke_results(), indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accion", choices=["record"])
    parser.parse_args()
    record()
