"""Horizonte por defecto del contrato v1 (decisión C2 de docs/backend/api_v1_decisiones.md)

Revisión: 0004_v1
Anterior: 0003_oe2

Solo datos: siembra parametro_sistema.horizonte_por_defecto, que lee GET /configuracion,
igual que las semillas de la 0003. No cambia tablas, columnas, índices ni permisos.
"""

from alembic import op


revision = '0004_v1'
down_revision = '0003_oe2'
branch_labels = None
depends_on = None

# Copia literal: la migración no cambia si el código cambia.
CLAVE = 'horizonte_por_defecto'
VALOR = '{"horizonte": 4}'
DESCRIPCION = 'Horizonte (semanas) que el frontend muestra por defecto; objetivo de la tesis: 4'


def upgrade():
    """Siembra el parámetro como JSON literal, igual en ambos motores."""
    conversion = '::jsonb' if op.get_context().dialect.name == 'postgresql' else ''
    op.execute(f"INSERT INTO parametro_sistema (clave, valor, descripcion) "
               f"VALUES ('{CLAVE}', '{VALOR}'{conversion}, '{DESCRIPCION}')")


def downgrade():
    """Quita solo el parámetro sembrado por esta revisión."""
    op.execute(f"DELETE FROM parametro_sistema WHERE clave = '{CLAVE}'")
