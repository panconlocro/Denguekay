"""Esquema inicial del backend

Revisión: 0001_backend
Anterior: ninguna
"""

from alembic import op
import sqlalchemy as sa


revision = '0001_backend'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Aplica el cambio de esquema."""
    # Esquema inicial generado por Alembic y revisado para ambos motores.
    op.create_table('carga_datos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('huella', sa.String(length=64), nullable=False),
    sa.Column('hashes_entrada', sa.JSON(), nullable=False),
    sa.Column('validacion_gx', sa.JSON(), nullable=False),
    sa.Column('fecha_corte_datos', sa.Date(), nullable=False),
    sa.Column('filas_distritos', sa.Integer(), nullable=False),
    sa.Column('filas_observaciones', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_carga_datos')),
    sa.UniqueConstraint('huella', name=op.f('uq_carga_datos_huella'))
    )
    op.create_table('distrito',
    sa.Column('ubigeo', sa.String(length=6), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.Column('provincia', sa.String(length=100), nullable=False),
    sa.Column('lat', sa.Float(), nullable=True),
    sa.Column('lon', sa.Float(), nullable=True),
    sa.Column('geometria', sa.JSON(none_as_null=True), nullable=True),
    sa.Column('motivo_geometria', sa.Text(), nullable=True),
    sa.Column('fecha_actualizacion', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("length(ubigeo) = 6 AND substr(ubigeo, 1, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 2, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 3, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 4, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 5, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 6, 1) BETWEEN '0' AND '9'", name=op.f('ck_distrito_ubigeo_seis_digitos')),
    sa.CheckConstraint('lat BETWEEN -90 AND 90', name=op.f('ck_distrito_lat_valida')),
    sa.CheckConstraint('lon BETWEEN -180 AND 180', name=op.f('ck_distrito_lon_valida')),
    sa.PrimaryKeyConstraint('ubigeo', name=op.f('pk_distrito'))
    )
    op.create_table('ejecucion_prediccion',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fecha_corte_datos', sa.Date(), nullable=False),
    sa.Column('versiones_usadas', sa.JSON(), nullable=False),
    sa.Column('hashes_entrada', sa.JSON(), nullable=False),
    sa.Column('huella', sa.String(length=64), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('filas_generadas', sa.Integer(), nullable=False),
    sa.Column('duracion_segundos', sa.Float(), nullable=False),
    sa.Column('motivo', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ejecucion_prediccion')),
    sa.UniqueConstraint('huella', name=op.f('uq_ejecucion_prediccion_huella'))
    )
    op.create_table('version_modelo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('horizonte', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('variante', sa.String(length=80), nullable=False),
    sa.Column('columnas', sa.JSON(), nullable=False),
    sa.Column('hiperparametros', sa.JSON(), nullable=False),
    sa.Column('umbral_probabilidad', sa.Float(), nullable=True),
    sa.Column('entrenamiento_inicio', sa.Date(), nullable=False),
    sa.Column('entrenamiento_corte', sa.Date(), nullable=False),
    sa.Column('metricas_evaluacion', sa.JSON(), nullable=False),
    sa.Column('particion_temporal', sa.JSON(), nullable=False),
    sa.Column('mlflow_run_id', sa.String(length=64), nullable=True),
    sa.Column('sha256_gold', sa.String(length=64), nullable=False),
    sa.Column('sha256_manifiesto', sa.String(length=64), nullable=False),
    sa.Column('device', sa.String(length=40), nullable=False),
    sa.Column('version_xgboost', sa.String(length=40), nullable=True),
    sa.Column('plataforma', sa.String(length=200), nullable=False),
    sa.Column('fecha_creacion', sa.DateTime(timezone=True), nullable=False),
    sa.Column('activa', sa.Boolean(), nullable=False),
    sa.Column('artefacto', sa.JSON(), nullable=False),
    sa.CheckConstraint("tipo IN ('clasificacion','regresion','persistencia')", name=op.f('ck_version_modelo_tipo_valido')),
    sa.CheckConstraint('horizonte BETWEEN 2 AND 4', name=op.f('ck_version_modelo_horizonte_valido')),
    sa.CheckConstraint('umbral_probabilidad BETWEEN 0 AND 1', name=op.f('ck_version_modelo_umbral_valido')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_version_modelo'))
    )
    with op.batch_alter_table('version_modelo', schema=None) as batch_op:
        batch_op.create_index('ix_version_horizonte_tipo', ['horizonte', 'tipo', 'activa'], unique=False)

    op.create_table('activacion_modelo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version_anterior_id', sa.Integer(), nullable=True),
    sa.Column('version_nueva_id', sa.Integer(), nullable=False),
    sa.Column('ejecucion_id', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.DateTime(timezone=True), nullable=False),
    sa.Column('motivo', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['ejecucion_id'], ['ejecucion_prediccion.id'], name=op.f('fk_activacion_modelo_ejecucion_id_ejecucion_prediccion')),
    sa.ForeignKeyConstraint(['version_anterior_id'], ['version_modelo.id'], name=op.f('fk_activacion_modelo_version_anterior_id_version_modelo')),
    sa.ForeignKeyConstraint(['version_nueva_id'], ['version_modelo.id'], name=op.f('fk_activacion_modelo_version_nueva_id_version_modelo')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_activacion_modelo'))
    )
    op.create_table('importancia_variable',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version_modelo_id', sa.Integer(), nullable=False),
    sa.Column('variable', sa.String(length=100), nullable=False),
    sa.Column('importancia', sa.Float(), nullable=False),
    sa.Column('rango', sa.Integer(), nullable=False),
    sa.CheckConstraint('importancia >= 0 AND rango >= 1', name=op.f('ck_importancia_variable_importancia_valida')),
    sa.ForeignKeyConstraint(['version_modelo_id'], ['version_modelo.id'], name=op.f('fk_importancia_variable_version_modelo_id_version_modelo')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_importancia_variable')),
    sa.UniqueConstraint('version_modelo_id', 'variable', name=op.f('uq_importancia_variable_version_modelo_id'))
    )
    op.create_table('observacion_semanal',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ubigeo', sa.String(length=6), nullable=False),
    sa.Column('anio', sa.Integer(), nullable=False),
    sa.Column('semana', sa.Integer(), nullable=False),
    sa.Column('semana_inicio', sa.Date(), nullable=False),
    sa.Column('casos', sa.Integer(), nullable=True),
    sa.Column('brote', sa.Boolean(), nullable=True),
    sa.Column('umbral_brote_casos', sa.Float(), nullable=True),
    sa.Column('procedencia', sa.String(length=80), nullable=False),
    sa.Column('motivo', sa.Text(), nullable=True),
    sa.Column('carga_id', sa.Integer(), nullable=False),
    sa.Column('fecha_corte_datos', sa.Date(), nullable=False),
    sa.Column('fecha_actualizacion', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("length(ubigeo) = 6 AND substr(ubigeo, 1, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 2, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 3, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 4, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 5, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 6, 1) BETWEEN '0' AND '9'", name=op.f('ck_observacion_semanal_ubigeo_seis_digitos')),
    sa.CheckConstraint('casos >= 0', name=op.f('ck_observacion_semanal_casos_no_negativos')),
    sa.CheckConstraint('casos IS NOT NULL OR motivo IS NOT NULL', name=op.f('ck_observacion_semanal_faltante_con_motivo')),
    sa.CheckConstraint('semana BETWEEN 1 AND 53', name=op.f('ck_observacion_semanal_semana_valida')),
    sa.CheckConstraint('umbral_brote_casos >= 0', name=op.f('ck_observacion_semanal_umbral_no_negativo')),
    sa.ForeignKeyConstraint(['carga_id'], ['carga_datos.id'], name=op.f('fk_observacion_semanal_carga_id_carga_datos')),
    sa.ForeignKeyConstraint(['ubigeo'], ['distrito.ubigeo'], name=op.f('fk_observacion_semanal_ubigeo_distrito')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_observacion_semanal')),
    sa.UniqueConstraint('ubigeo', 'anio', 'semana', name=op.f('uq_observacion_semanal_ubigeo'))
    )
    with op.batch_alter_table('observacion_semanal', schema=None) as batch_op:
        batch_op.create_index('ix_observacion_distrito_fecha', ['ubigeo', 'semana_inicio'], unique=False)

    op.create_table('prediccion',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ubigeo', sa.String(length=6), nullable=False),
    sa.Column('horizonte', sa.Integer(), nullable=False),
    sa.Column('anio', sa.Integer(), nullable=False),
    sa.Column('semana', sa.Integer(), nullable=False),
    sa.Column('semana_inicio', sa.Date(), nullable=False),
    sa.Column('origen_cierre', sa.Date(), nullable=False),
    sa.Column('probabilidad', sa.Float(), nullable=True),
    sa.Column('nivel_riesgo', sa.String(length=20), nullable=True),
    sa.Column('casos_estimados', sa.Float(), nullable=True),
    sa.Column('alerta_modelo', sa.Boolean(), nullable=True),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('version_clasificacion_id', sa.Integer(), nullable=True),
    sa.Column('version_regresion_id', sa.Integer(), nullable=True),
    sa.Column('ejecucion_id', sa.Integer(), nullable=False),
    sa.Column('caracteristicas', sa.JSON(), nullable=False),
    sa.Column('motivo', sa.Text(), nullable=True),
    sa.Column('fecha_actualizacion', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("length(ubigeo) = 6 AND substr(ubigeo, 1, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 2, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 3, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 4, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 5, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 6, 1) BETWEEN '0' AND '9'", name=op.f('ck_prediccion_ubigeo_seis_digitos')),
    sa.CheckConstraint("tipo IN ('vigente','retrospectiva')", name=op.f('ck_prediccion_tipo_valido')),
    sa.CheckConstraint('casos_estimados >= 0', name=op.f('ck_prediccion_casos_no_negativos')),
    sa.CheckConstraint('horizonte BETWEEN 2 AND 4', name=op.f('ck_prediccion_horizonte_valido')),
    sa.CheckConstraint('origen_cierre < semana_inicio', name=op.f('ck_prediccion_origen_anterior_objetivo')),
    sa.CheckConstraint('probabilidad BETWEEN 0 AND 1', name=op.f('ck_prediccion_probabilidad_valida')),
    sa.CheckConstraint('semana BETWEEN 1 AND 53', name=op.f('ck_prediccion_semana_valida')),
    sa.ForeignKeyConstraint(['ejecucion_id'], ['ejecucion_prediccion.id'], name=op.f('fk_prediccion_ejecucion_id_ejecucion_prediccion')),
    sa.ForeignKeyConstraint(['ubigeo'], ['distrito.ubigeo'], name=op.f('fk_prediccion_ubigeo_distrito')),
    sa.ForeignKeyConstraint(['version_clasificacion_id'], ['version_modelo.id'], name=op.f('fk_prediccion_version_clasificacion_id_version_modelo')),
    sa.ForeignKeyConstraint(['version_regresion_id'], ['version_modelo.id'], name=op.f('fk_prediccion_version_regresion_id_version_modelo')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_prediccion')),
    sa.UniqueConstraint('ejecucion_id', 'ubigeo', 'horizonte', 'semana_inicio', 'tipo', name=op.f('uq_prediccion_ejecucion_id'))
    )
    with op.batch_alter_table('prediccion', schema=None) as batch_op:
        batch_op.create_index('ix_prediccion_horizonte_fecha', ['horizonte', 'semana_inicio'], unique=False)
        batch_op.create_index('ix_prediccion_ubigeo_horizonte', ['ubigeo', 'horizonte'], unique=False)

    op.create_table('alerta',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('prediccion_id', sa.Integer(), nullable=False),
    sa.Column('ubigeo', sa.String(length=6), nullable=False),
    sa.Column('horizonte', sa.Integer(), nullable=False),
    sa.Column('semana_inicio', sa.Date(), nullable=False),
    sa.Column('nivel', sa.String(length=20), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('fecha_generacion', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fecha_retiro', sa.DateTime(timezone=True), nullable=True),
    sa.Column('motivo', sa.Text(), nullable=True),
    sa.CheckConstraint("estado IN ('activa','retirada')", name=op.f('ck_alerta_estado_valido')),
    sa.CheckConstraint("length(ubigeo) = 6 AND substr(ubigeo, 1, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 2, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 3, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 4, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 5, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 6, 1) BETWEEN '0' AND '9'", name=op.f('ck_alerta_ubigeo_seis_digitos')),
    sa.ForeignKeyConstraint(['prediccion_id'], ['prediccion.id'], name=op.f('fk_alerta_prediccion_id_prediccion')),
    sa.ForeignKeyConstraint(['ubigeo'], ['distrito.ubigeo'], name=op.f('fk_alerta_ubigeo_distrito')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_alerta')),
    sa.UniqueConstraint('prediccion_id', name=op.f('uq_alerta_prediccion_id'))
    )
    with op.batch_alter_table('alerta', schema=None) as batch_op:
        batch_op.create_index('ix_alerta_horizonte_estado', ['horizonte', 'estado'], unique=False)

    # Fin del cambio de esquema.


def downgrade():
    """Revierte el cambio; requiere respaldo si existen datos."""
    # Esquema inicial generado por Alembic y revisado para ambos motores.
    with op.batch_alter_table('alerta', schema=None) as batch_op:
        batch_op.drop_index('ix_alerta_horizonte_estado')

    op.drop_table('alerta')
    with op.batch_alter_table('prediccion', schema=None) as batch_op:
        batch_op.drop_index('ix_prediccion_ubigeo_horizonte')
        batch_op.drop_index('ix_prediccion_horizonte_fecha')

    op.drop_table('prediccion')
    with op.batch_alter_table('observacion_semanal', schema=None) as batch_op:
        batch_op.drop_index('ix_observacion_distrito_fecha')

    op.drop_table('observacion_semanal')
    op.drop_table('importancia_variable')
    op.drop_table('activacion_modelo')
    with op.batch_alter_table('version_modelo', schema=None) as batch_op:
        batch_op.drop_index('ix_version_horizonte_tipo')

    op.drop_table('version_modelo')
    op.drop_table('ejecucion_prediccion')
    op.drop_table('distrito')
    op.drop_table('carga_datos')
    # Fin del cambio de esquema.
