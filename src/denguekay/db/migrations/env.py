"""Alembic connection; the URL comes from the same environment as the application."""

from alembic import context

from denguekay.db.settings import get_url
from denguekay.db.models import Base
from denguekay.db.session import make_engine


if context.is_offline_mode():
    # Offline mode only needs the dialect: it accepts an injected URL without credentials.
    url = context.config.attributes.get("url") or get_url()
    context.configure(url=url, target_metadata=Base.metadata,
                      literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = context.config.attributes.get("motor")
    owned = engine is None
    if owned:
        engine = make_engine()
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata,
                              compare_type=True, render_as_batch=connection.dialect.name == "sqlite")
            with context.begin_transaction():
                context.run_migrations()
    finally:
        if owned:
            engine.dispose()
