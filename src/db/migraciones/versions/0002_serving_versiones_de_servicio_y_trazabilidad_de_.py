"""Versiones de servicio y trazabilidad de inferencia

Revisión: 0002_serving
Anterior: 0001_backend
"""

from alembic import op
import sqlalchemy as sa
import hashlib

revision = '0002_serving'
down_revision = '0001_backend'
branch_labels = None
depends_on = None


def upgrade():
    """Aplica el cambio de esquema."""
    # Se preservan las observaciones y se admiten versiones históricas sin booster.
    with op.batch_alter_table('ejecucion_prediccion', schema=None) as batch_op:
        batch_op.add_column(sa.Column('resumen', sa.JSON(), nullable=False, server_default='{}'))

    with op.batch_alter_table('prediccion', schema=None) as batch_op:
        batch_op.add_column(sa.Column('casos_persistencia', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('version_persistencia_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(batch_op.f('fk_prediccion_version_persistencia_id_version_modelo'), 'version_modelo', ['version_persistencia_id'], ['id'])

    with op.batch_alter_table('version_modelo', schema=None) as batch_op:
        batch_op.add_column(sa.Column('huella', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('origen', sa.String(length=20), nullable=False, server_default='servicio'))
        batch_op.add_column(sa.Column('bloque', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('criterios_validacion', sa.JSON(), nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column('motivo_artefacto', sa.Text(), nullable=True))
        batch_op.alter_column('plataforma',
               existing_type=sa.VARCHAR(length=200),
               nullable=True)
        batch_op.alter_column('artefacto',
               existing_type=sa.JSON(),
               nullable=True)
        batch_op.create_index('uq_version_activa', ['horizonte', 'tipo'], unique=True, sqlite_where=sa.text('activa = 1'), postgresql_where=sa.text('activa'))
        batch_op.create_unique_constraint(batch_op.f('uq_version_modelo_huella'), ['huella'])
        batch_op.create_check_constraint('origen_valido', "origen IN ('servicio','retrospectiva')")
        batch_op.create_check_constraint('activa_con_artefacto', "NOT activa OR (artefacto IS NOT NULL AND origen = 'servicio')")

    # La fase 1 no publicó modelos. Se contempla una identidad de migración
    # para una versión preexistente, sin inventar su hash de gold o booster.
    conexion = op.get_bind()
    for identificador in conexion.execute(sa.text('SELECT id FROM version_modelo')).scalars():
        huella = hashlib.sha256(f'version_previa_fase1:{identificador}'.encode()).hexdigest()
        conexion.execute(sa.text('UPDATE version_modelo SET huella = :huella WHERE id = :id'),
                         {'huella': huella, 'id': identificador})
    with op.batch_alter_table('version_modelo') as batch_op:
        batch_op.alter_column('huella', existing_type=sa.String(64), nullable=False)



def downgrade():
    """Revierte el cambio; requiere respaldo si existen datos."""
    with op.batch_alter_table('version_modelo', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('ck_version_modelo_activa_con_artefacto'), type_='check')
        batch_op.drop_constraint(batch_op.f('ck_version_modelo_origen_valido'), type_='check')
        batch_op.drop_constraint(batch_op.f('uq_version_modelo_huella'), type_='unique')
        batch_op.drop_index('uq_version_activa', sqlite_where=sa.text('activa = 1'), postgresql_where=sa.text('activa'))
        batch_op.alter_column('artefacto',
               existing_type=sa.JSON(),
               nullable=False)
        batch_op.alter_column('plataforma',
               existing_type=sa.VARCHAR(length=200),
               nullable=False)
        batch_op.drop_column('motivo_artefacto')
        batch_op.drop_column('criterios_validacion')
        batch_op.drop_column('bloque')
        batch_op.drop_column('origen')
        batch_op.drop_column('huella')

    with op.batch_alter_table('prediccion', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_prediccion_version_persistencia_id_version_modelo'), type_='foreignkey')
        batch_op.drop_column('version_persistencia_id')
        batch_op.drop_column('casos_persistencia')

    with op.batch_alter_table('ejecucion_prediccion', schema=None) as batch_op:
        batch_op.drop_column('resumen')
