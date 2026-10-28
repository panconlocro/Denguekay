"""Generate the offline SQL (alembic upgrade --sql) of the OE2 migration as evidence.

It does not connect to any database nor read .env: it uses a dummy URL only to
choose the PostgreSQL dialect. It covers 0002_serving -> head because the
historical migration 0002 queries data and does not support offline mode from base.
"""

import contextlib
import io

from alembic import command
from alembic.config import Config

from denguekay.config.paths import ALEMBIC_CONFIG, OE2_MIGRATION_SQL

DIALECT_URL = "postgresql+psycopg://offline@localhost/sin_conexion"


def export(destination=OE2_MIGRATION_SQL, revision_range="0002_serving:head"):
    output = io.StringIO()
    config = Config(str(ALEMBIC_CONFIG), stdout=output)
    config.attributes["url"] = DIALECT_URL
    with contextlib.redirect_stdout(output):
        command.upgrade(config, revision_range, sql=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(output.getvalue(), encoding="utf-8")
    return destination


if __name__ == "__main__":
    print(export())
