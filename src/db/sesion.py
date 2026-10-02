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


def upsert(sesion, tabla, filas, claves, actualizar=None, lote=2000):
    """INSERT ... ON CONFLICT (claves) DO UPDATE portable entre SQLite y PostgreSQL.

    ``actualizar`` limita las columnas que se sobrescriben; por defecto, todas
    las de la fila salvo las claves. Con ``actualizar=()`` no se modifica nada
    (ON CONFLICT DO NOTHING). Inserta por lotes para no exceder parámetros.
    """
    if not filas:
        return
    if sesion.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    columnas = list(filas[0])
    actualizables = [c for c in (columnas if actualizar is None else actualizar) if c not in claves]
    for inicio in range(0, len(filas), lote):
        consulta = insert(tabla).values(filas[inicio:inicio + lote])
        if actualizables:
            consulta = consulta.on_conflict_do_update(
                index_elements=list(claves), set_={c: consulta.excluded[c] for c in actualizables})
        else:
            consulta = consulta.on_conflict_do_nothing(index_elements=list(claves))
        sesion.execute(consulta)
