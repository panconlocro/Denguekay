"""Exporta el contrato con ejemplos reales, sin modificar la base de datos."""

import json

from src.api.main import crear_app
from src.api.openapi import especificacion
from src.db.sesion import crear_fabrica_sesiones, crear_motor
from src.utils.paths import OPENAPI_JSON


def exportar(motor=None):
    """Exige conexión y tablas reales antes de escribir el archivo versionable."""
    propio = motor is None
    motor = motor if motor is not None else crear_motor()
    try:
        app = crear_app(motor=motor)
        app.state.fabrica_sesiones = crear_fabrica_sesiones(motor)
        # Fuerza una consulta antes de exportar; no acepta una exportación vacía por BD caída.
        from src.api.consultas import salud
        with app.state.fabrica_sesiones() as sesion:
            salud(sesion, app.version)
        schema = especificacion(app)
        OPENAPI_JSON.parent.mkdir(parents=True, exist_ok=True)
        OPENAPI_JSON.write_text(json.dumps(schema, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        return {"archivo": str(OPENAPI_JSON.relative_to(OPENAPI_JSON.parents[2])),
                "rutas": len(schema["paths"]), "operaciones": sum(len(p) for p in schema["paths"].values())}
    finally:
        if propio:
            motor.dispose()


if __name__ == "__main__":
    try:
        print(json.dumps(exportar(), ensure_ascii=False))
    except Exception:
        raise SystemExit("No se pudo exportar OpenAPI; comprueba DATABASE_URL, la conexión y las migraciones")
