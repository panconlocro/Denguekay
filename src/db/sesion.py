"""Motores y transacciones portables entre SQLite y PostgreSQL."""

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.configuracion import obtener_url


def crear_motor(url=None):
    """Activa claves foráneas en SQLite y comprueba conexiones del pool."""
    url = url if url is not None else obtener_url()
    from sqlalchemy.engine import make_url

    url = make_url(url)
    opciones = {"pool_pre_ping": True, "hide_parameters": True}
    if url.get_backend_name() == "sqlite":
        opciones["connect_args"] = {"check_same_thread": False}
        if url.database in {None, "", ":memory:"}:
            opciones["poolclass"] = StaticPool
    else:
        opciones["connect_args"] = {"connect_timeout": 10}
    motor = create_engine(url, **opciones)
    if url.get_backend_name() == "sqlite":
        @event.listens_for(motor, "connect")
        def configurar_sqlite(conexion, _):
            cursor = conexion.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.close()
    return motor


def crear_fabrica_sesiones(motor):
    """Crea sesiones sin caducar objetos al confirmar una transacción."""
    return sessionmaker(bind=motor, expire_on_commit=False)


@contextmanager
def transaccion(motor):
    """Confirma todo el lote o revierte todos sus cambios si falla."""
    with crear_fabrica_sesiones(motor)() as sesion:
        with sesion.begin():
            yield sesion
