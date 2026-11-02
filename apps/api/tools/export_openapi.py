"""Export the contract: openapi.json with real examples, or the frozen openapi_v1.json without them.

``python -m apps.api.tools.export_openapi`` writes openapi.json from DATABASE_URL (read-only).
``python -m apps.api.tools.export_openapi --contrato`` writes openapi_v1.json without a database;
run it only after raising CONTRACT_VERSION for an additive change (docs/backend/contrato_api.md).
"""

import argparse
import json

from apps.api.main import create_app
from apps.api.openapi import specification
from denguekay.db.session import create_session_factory, make_engine
from denguekay.config.paths import OPENAPI_JSON, OPENAPI_V1_JSON


def write(path, schema):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return {"archivo": str(path.relative_to(path.parents[2])),
            "rutas": len(schema["paths"]), "operaciones": sum(len(p) for p in schema["paths"].values())}


def export(engine=None):
    """Require a connection and real tables before writing the versioned file."""
    owned = engine is None
    engine = engine if engine is not None else make_engine()
    try:
        app = create_app(engine=engine)
        app.state.session_factory = create_session_factory(engine)
        # Force a query before exporting; an empty export because the database is down is not accepted.
        from apps.api.queries import health
        with app.state.session_factory() as session:
            health(session, app.version)
        return write(OPENAPI_JSON, specification(app))
    finally:
        if owned:
            engine.dispose()


def export_contract():
    """The contract as the API serves it without a database (no examples): the guard's reference."""
    return write(OPENAPI_V1_JSON, specification(create_app()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contrato", action="store_true", help="Escribe openapi_v1.json (sin BD ni ejemplos)")
    options = parser.parse_args()
    try:
        print(json.dumps(export_contract() if options.contrato else export(), ensure_ascii=False))
    except Exception:
        raise SystemExit("No se pudo exportar OpenAPI; comprueba DATABASE_URL, la conexión y las migraciones")
