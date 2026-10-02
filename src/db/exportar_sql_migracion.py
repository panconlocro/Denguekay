"""Genera el SQL offline (alembic upgrade --sql) de la migración OE2 como evidencia.

No se conecta a ninguna BD ni lee .env: usa una URL ficticia solo para elegir
el dialecto PostgreSQL. Cubre 0002_serving -> head porque la migración
histórica 0002 consulta datos y no admite el modo offline desde base.
"""

import contextlib
import io

from alembic import command
from alembic.config import Config

from src.utils.paths import ALEMBIC_CONFIG, MIGRACION_OE2_SQL

URL_DIALECTO = "postgresql+psycopg://offline@localhost/sin_conexion"


def exportar(destino=MIGRACION_OE2_SQL, rango="0002_serving:head"):
    salida = io.StringIO()
    config = Config(str(ALEMBIC_CONFIG), stdout=salida)
    config.attributes["url"] = URL_DIALECTO
    with contextlib.redirect_stdout(salida):
        command.upgrade(config, rango, sql=True)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(salida.getvalue(), encoding="utf-8")
    return destino


if __name__ == "__main__":
    print(exportar())
