"""Export the contract with real examples, without modifying the database."""

import json

from apps.api.main import create_app
from apps.api.openapi import specification
from denguekay.db.session import create_session_factory, make_engine
from denguekay.config.paths import OPENAPI_JSON


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
        schema = specification(app)
        OPENAPI_JSON.parent.mkdir(parents=True, exist_ok=True)
        OPENAPI_JSON.write_text(json.dumps(schema, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        return {"archivo": str(OPENAPI_JSON.relative_to(OPENAPI_JSON.parents[2])),
                "rutas": len(schema["paths"]), "operaciones": sum(len(p) for p in schema["paths"].values())}
    finally:
        if owned:
            engine.dispose()


if __name__ == "__main__":
    try:
        print(json.dumps(export(), ensure_ascii=False))
    except Exception:
        raise SystemExit("No se pudo exportar OpenAPI; comprueba DATABASE_URL, la conexión y las migraciones")
