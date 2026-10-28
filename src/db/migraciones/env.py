"""Conexión de Alembic; la URL se obtiene del mismo entorno que la aplicación."""

from alembic import context

from src.db.configuracion import obtener_url
from src.db.modelos import Base
from src.db.sesion import crear_motor


if context.is_offline_mode():
    # El modo offline solo necesita el dialecto: admite una URL inyectada sin credenciales.
    url = context.config.attributes.get("url") or obtener_url()
    context.configure(url=url, target_metadata=Base.metadata,
                      literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    motor = context.config.attributes.get("motor")
    propio = motor is None
    if propio:
        motor = crear_motor()
    try:
        with motor.connect() as conexion:
            context.configure(connection=conexion, target_metadata=Base.metadata,
                              compare_type=True, render_as_batch=conexion.dialect.name == "sqlite")
            with context.begin_transaction():
                context.run_migrations()
    finally:
        if propio:
            motor.dispose()
