"""Engines and transactions portable between SQLite and PostgreSQL."""

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from denguekay.db.settings import get_url


def make_engine(url=None):
    """Turn on foreign keys in SQLite and check the pool connections."""
    url = url if url is not None else get_url()
    from sqlalchemy.engine import make_url

    url = make_url(url)
    options = {"pool_pre_ping": True, "hide_parameters": True}
    if url.get_backend_name() == "sqlite":
        options["connect_args"] = {"check_same_thread": False}
        if url.database in {None, "", ":memory:"}:
            options["poolclass"] = StaticPool
    else:
        options["connect_args"] = {"connect_timeout": 10}
    engine = create_engine(url, **options)
    if url.get_backend_name() == "sqlite":
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.close()
    return engine


def create_session_factory(engine):
    """Create sessions that do not expire objects when a transaction commits."""
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def transaction(engine):
    """Commit the whole batch, or roll back all of its changes if it fails."""
    with create_session_factory(engine)() as session:
        with session.begin():
            yield session


def upsert(session, table, rows, keys, update=None, batch=2000):
    """INSERT ... ON CONFLICT (keys) DO UPDATE, portable between SQLite and PostgreSQL.

    ``update`` limits the columns that are overwritten; by default, every column of
    the row except the keys. With ``update=()`` nothing is modified
    (ON CONFLICT DO NOTHING). It inserts in batches so as not to exceed the parameters.
    """
    if not rows:
        return
    if session.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    columns = list(rows[0])
    updatable = [c for c in (columns if update is None else update) if c not in keys]
    for start in range(0, len(rows), batch):
        query = insert(table).values(rows[start:start + batch])
        if updatable:
            query = query.on_conflict_do_update(
                index_elements=list(keys), set_={c: query.excluded[c] for c in updatable})
        else:
            query = query.on_conflict_do_nothing(index_elements=list(keys))
        session.execute(query)
