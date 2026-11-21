"""Fuente de casos ``datos_abiertos_confirmados`` para las semanas de la V4 anteriores a 2025

Revisión: 0012_v4
Anterior: 0011_v4

Agrega el valor ``datos_abiertos_confirmados`` al tipo ``fuente_casos_t`` de ``observacion_semanal.fuente_casos``: las
semanas de la V4 anteriores a 2025 salen del CSV «Vigilancia epidemiológica de dengue» (casos confirmados), no del Excel
histórico de v0 a v3 (``excel_historico``, que se conserva). Cambio aditivo del contrato (API 1.3.0). No cambia ningún dato.

PostgreSQL: ``ALTER TYPE ... ADD VALUE``. El downgrade reasigna esas filas a ``excel_historico`` y recrea el tipo, porque
PostgreSQL no permite quitar un valor de un ENUM. SQLite (solo pruebas): se reescribe el texto del CHECK en
``sqlite_master``, como en el procedimiento documentado de SQLite para cambiar un CHECK sin copiar la tabla; no se usa
``batch_alter_table`` porque al recrear la tabla convierte en restricciones de tabla los CHECK de columna de 0005 y 0007,
y el downgrade de 0007 (``DROP COLUMN``) deja de funcionar.
"""

from alembic import op
from sqlalchemy import text

revision = "0012_v4"
down_revision = "0011_v4"
branch_labels = None
depends_on = None

NEW_VALUE = "datos_abiertos_confirmados"
OLD = ("excel_historico", "sala_situacional")
NEW = ("excel_historico", NEW_VALUE, "sala_situacional")


def _list(values):
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def _rewrite_check(before, after):
    """Replace the value list of the CHECK and the declared length of ``fuente_casos`` in the table definition (SQLite
    keeps both as text in ``sqlite_master``; the longest new value does not fit the VARCHAR(16) of 0003)."""
    connection = op.get_bind()
    version = connection.execute(text("PRAGMA schema_version")).scalar_one()
    sql = connection.execute(text("SELECT sql FROM sqlite_master WHERE type = 'table' "
                                  "AND name = 'observacion_semanal'")).scalar_one()
    swaps = [(f"fuente_casos IN {_list(before)}", f"fuente_casos IN {_list(after)}"),
             (f"fuente_casos VARCHAR({max(map(len, before))})", f"fuente_casos VARCHAR({max(map(len, after))})")]
    for old, new in swaps:
        if sql.count(old) != 1:
            raise RuntimeError(f"No se encontró «{old}» en la definición de observacion_semanal")
        sql = sql.replace(old, new)
    connection.execute(text("PRAGMA writable_schema = ON"))
    connection.execute(text("UPDATE sqlite_master SET sql = :sql WHERE type = 'table' "
                            "AND name = 'observacion_semanal'"), {"sql": sql})
    connection.execute(text(f"PRAGMA schema_version = {version + 1}"))
    connection.execute(text("PRAGMA writable_schema = OFF"))


def upgrade():
    if op.get_context().dialect.name == "postgresql":
        op.execute(f"ALTER TYPE fuente_casos_t ADD VALUE IF NOT EXISTS '{NEW_VALUE}' AFTER 'excel_historico'")
    else:
        _rewrite_check(OLD, NEW)


def downgrade():
    op.execute(f"UPDATE observacion_semanal SET fuente_casos = 'excel_historico' WHERE fuente_casos = '{NEW_VALUE}'")
    if op.get_context().dialect.name == "postgresql":
        op.execute("ALTER TYPE fuente_casos_t RENAME TO fuente_casos_t_con_datos_abiertos")
        op.execute("CREATE TYPE fuente_casos_t AS ENUM ('excel_historico', 'sala_situacional')")
        op.execute("ALTER TABLE observacion_semanal ALTER COLUMN fuente_casos TYPE fuente_casos_t "
                   "USING fuente_casos::text::fuente_casos_t")
        op.execute("DROP TYPE fuente_casos_t_con_datos_abiertos")
    else:
        _rewrite_check(NEW, OLD)
