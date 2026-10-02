"""Esquema del documento OE2 (Anexo B, ddl_oe2.sql)

Revisión: 0003_oe2
Anterior: 0002_serving

Reemplaza el esquema de 0001/0002: la BD local se recarga desde las fuentes
(decisión e de la Fase 0). En PostgreSQL crea ENUM nativos, CHECK con regex,
RLS, roles de servicio, permisos y políticas; en SQLite los ENUM son CHECK y
se omiten RLS y roles. Las desviaciones están en docs/backend/desviaciones_oe2.md.
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0003_oe2'
down_revision = '0002_serving'
branch_labels = None
depends_on = None

# Copia literal (no importada del ORM) para que la migración no cambie si el código cambia.
ENUMS = {
    'fuente_casos_t': ('excel_historico', 'sala_situacional'),
    'cobertura_t': ('verificado', 'sin_registro', 'pendiente'),
    'tarea_t': ('clasificacion', 'regresion'),
    'estado_version_t': ('candidata', 'activa', 'archivada', 'rechazada'),
    'tipo_ejecucion_t': ('ingesta', 'inferencia', 'reentrenamiento', 'mantenimiento'),
    'estado_ejecucion_t': ('en_curso', 'exitosa', 'fallida'),
    'nivel_riesgo_t': ('bajo', 'medio', 'alto', 'muy_alto'),
    'estado_prediccion_t': ('disponible', 'no_disponible'),
    'estado_alerta_t': ('activa', 'retirada'),
    'cambio_alerta_t': ('nueva', 'se_mantiene', 'sube_nivel', 'baja_nivel'),
}

TABLAS_OE2 = ('provincia', 'distrito', 'semana_epidemiologica', 'observacion_semanal',
              'version_modelo', 'ejecucion', 'prediccion', 'alerta', 'parametro_sistema')
# Extensión aprobada: recibe la misma protección que las tablas del documento.
TABLAS_PROTEGIDAS = TABLAS_OE2 + ('importancia_variable',)

TABLAS_ANTERIORES = ('alerta', 'prediccion', 'activacion_modelo', 'importancia_variable',
                     'observacion_semanal', 'version_modelo', 'ejecucion_prediccion',
                     'carga_datos', 'distrito')

PARAMETROS = (
    ('regla_brote', '{"anios_previos": 5, "k_desviaciones": 1.5, "minimo_casos": 2}',
     'Umbral = media de la misma semana en 5 años previos + k DE; mínimo de casos'),
    ('cortes_riesgo', '{"medio": 0.25, "alto": 0.50, "muy_alto": 0.75}',
     'Cortes de probabilidad para el nivel de riesgo'),
    # "bloque": corrección aprobada del documento (el DDL no decía qué bloque decide).
    ('umbrales_aceptacion',
     '{"recall": 0.80, "precision": 0.60, "f1": 0.70, "razon_error_base": 0.85, "bloque": "temporada_2024"}',
     'Criterios para promover un modelo'),
)


def _es_postgresql():
    return op.get_context().dialect.name == 'postgresql'


def _enum(nombre):
    """ENUM nativo ya creado en PostgreSQL; VARCHAR con CHECK en SQLite."""
    if _es_postgresql():
        return postgresql.ENUM(*ENUMS[nombre], name=nombre, create_type=False)
    return sa.Enum(*ENUMS[nombre], name=nombre, native_enum=False, create_constraint=True)


def _json():
    return postgresql.JSONB() if _es_postgresql() else sa.JSON()


def _id(grande=True):
    """Identity GENERATED ALWAYS en PostgreSQL; INTEGER PRIMARY KEY en SQLite."""
    if _es_postgresql():
        return sa.BigInteger() if grande else sa.Integer(), sa.Identity(always=True)
    return sa.Integer(), None


def _columna_id(nombre, grande=True):
    tipo, identidad = _id(grande)
    argumentos = (identidad,) if identidad is not None else ()
    return sa.Column(nombre, tipo, *argumentos, nullable=False)


def _digitos(columna, n, nombre):
    """Nombre final (op.f): la convención de nombres no se vuelve a aplicar."""
    if _es_postgresql():
        return sa.CheckConstraint(f"{columna} ~ '^[0-9]{{{n}}}$'", name=op.f(nombre))
    partes = [f'length({columna}) = {n}'] + [
        f"substr({columna}, {i}, 1) BETWEEN '0' AND '9'" for i in range(1, n + 1)]
    return sa.CheckConstraint(' AND '.join(partes), name=op.f(nombre))


def _ahora():
    return sa.text('now()') if _es_postgresql() else sa.text('CURRENT_TIMESTAMP')


def _crear_tablas():
    tz = sa.DateTime(timezone=True)
    op.create_table('provincia',
        sa.Column('ubigeo_provincia', sa.CHAR(4), nullable=False),
        sa.Column('nombre', sa.String(80), nullable=False),
        sa.PrimaryKeyConstraint('ubigeo_provincia', name='pk_provincia'),
        _digitos('ubigeo_provincia', 4, 'ck_provincia_ubigeo_provincia_formato'))

    op.create_table('distrito',
        sa.Column('ubigeo', sa.CHAR(6), nullable=False),
        sa.Column('ubigeo_provincia', sa.CHAR(4), nullable=False),
        sa.Column('nombre', sa.String(80), nullable=False),
        sa.Column('latitud', sa.Numeric(9, 6), nullable=False),
        sa.Column('longitud', sa.Numeric(9, 6), nullable=False),
        sa.Column('poblacion_censo_2017', sa.Integer(), nullable=True),
        sa.Column('activo', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.PrimaryKeyConstraint('ubigeo', name='pk_distrito'),
        sa.ForeignKeyConstraint(['ubigeo_provincia'], ['provincia.ubigeo_provincia'],
                                name='fk_distrito_ubigeo_provincia_provincia'),
        _digitos('ubigeo', 6, 'ck_distrito_ubigeo_formato'),
        sa.CheckConstraint('latitud BETWEEN -6.5 AND -3.5', name=op.f('ck_distrito_latitud_piura')),
        sa.CheckConstraint('longitud BETWEEN -81.5 AND -79.0', name=op.f('ck_distrito_longitud_piura')),
        sa.CheckConstraint('poblacion_censo_2017 > 0', name=op.f('ck_distrito_poblacion_positiva')))

    fecha_fin = ('fecha_fin = fecha_inicio + 6' if _es_postgresql()
                 else "fecha_fin = date(fecha_inicio, '+6 days')")
    op.create_table('semana_epidemiologica',
        sa.Column('id_semana', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('anio', sa.SmallInteger(), nullable=False),
        sa.Column('semana', sa.SmallInteger(), nullable=False),
        sa.Column('fecha_inicio', sa.Date(), nullable=False),
        sa.Column('fecha_fin', sa.Date(), nullable=False),
        sa.Column('temporada', sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id_semana', name='pk_semana_epidemiologica'),
        sa.UniqueConstraint('anio', 'semana', name='uq_semana_epidemiologica_anio'),
        sa.CheckConstraint('semana BETWEEN 1 AND 53', name=op.f('ck_semana_epidemiologica_semana_valida')),
        sa.CheckConstraint(fecha_fin, name=op.f('ck_semana_epidemiologica_fecha_fin_valida')))

    op.create_table('ejecucion',
        _columna_id('id_ejecucion'),
        sa.Column('tipo', _enum('tipo_ejecucion_t'), nullable=False),
        sa.Column('estado', _enum('estado_ejecucion_t'), server_default='en_curso', nullable=False),
        sa.Column('id_semana_corte', sa.Integer(), nullable=True),
        sa.Column('inicio', tz, server_default=_ahora(), nullable=False),
        sa.Column('fin', tz, nullable=True),
        sa.Column('detalle', _json(), nullable=True),
        sa.Column('mensaje_error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id_ejecucion', name='pk_ejecucion'),
        sa.ForeignKeyConstraint(['id_semana_corte'], ['semana_epidemiologica.id_semana'],
                                name='fk_ejecucion_id_semana_corte_semana_epidemiologica'))
    op.create_index('ix_ejecucion_tipo_inicio', 'ejecucion', ['tipo', sa.text('inicio DESC')])
    if _es_postgresql():
        op.create_index('ux_ejecucion_huella_ingesta', 'ejecucion', [sa.text("(detalle ->> 'huella')")],
                        unique=True, postgresql_where=sa.text("tipo = 'ingesta' AND estado = 'exitosa'"))

    op.create_table('observacion_semanal',
        sa.Column('ubigeo', sa.CHAR(6), nullable=False),
        sa.Column('id_semana', sa.Integer(), nullable=False),
        sa.Column('casos_dengue', sa.Integer(), nullable=True),
        sa.Column('umbral_brote_casos', sa.Numeric(10, 2), nullable=True),
        sa.Column('brote', sa.Boolean(), nullable=True),
        sa.Column('temp_media_c', sa.Numeric(5, 2), nullable=True),
        sa.Column('temp_min_c', sa.Numeric(5, 2), nullable=True),
        sa.Column('temp_max_c', sa.Numeric(5, 2), nullable=True),
        sa.Column('precip_total_mm', sa.Numeric(7, 2), nullable=True),
        sa.Column('hum_rel_media_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('fuente_casos', _enum('fuente_casos_t'), nullable=False),
        sa.Column('estado_cobertura', _enum('cobertura_t'), nullable=False),
        sa.Column('fecha_extraccion', tz, nullable=False),
        sa.Column('id_ejecucion', sa.BigInteger() if _es_postgresql() else sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('ubigeo', 'id_semana', name='pk_observacion_semanal'),
        sa.ForeignKeyConstraint(['ubigeo'], ['distrito.ubigeo'], name='fk_observacion_semanal_ubigeo_distrito'),
        sa.ForeignKeyConstraint(['id_semana'], ['semana_epidemiologica.id_semana'],
                                name='fk_observacion_semanal_id_semana_semana_epidemiologica'),
        sa.ForeignKeyConstraint(['id_ejecucion'], ['ejecucion.id_ejecucion'],
                                name='fk_observacion_semanal_id_ejecucion_ejecucion'),
        sa.CheckConstraint('casos_dengue >= 0', name=op.f('ck_observacion_semanal_casos_no_negativos')),
        sa.CheckConstraint('umbral_brote_casos >= 0', name=op.f('ck_observacion_semanal_umbral_no_negativo')),
        sa.CheckConstraint('precip_total_mm BETWEEN 0 AND 1500', name=op.f('ck_observacion_semanal_precipitacion_valida')),
        sa.CheckConstraint('hum_rel_media_pct BETWEEN 0 AND 100', name=op.f('ck_observacion_semanal_humedad_valida')),
        sa.CheckConstraint('temp_min_c <= temp_media_c AND temp_media_c <= temp_max_c',
                           name=op.f('ck_observacion_semanal_temperaturas_ordenadas')))
    op.create_index('ix_obs_semana', 'observacion_semanal', ['id_semana'])

    op.create_table('version_modelo',
        _columna_id('id_version', grande=False),
        sa.Column('codigo', sa.String(20), nullable=False),
        sa.Column('tarea', _enum('tarea_t'), nullable=False),
        sa.Column('horizonte', sa.SmallInteger(), nullable=False),
        sa.Column('algoritmo', sa.String(40), nullable=False),
        sa.Column('variables', _json(), nullable=False),
        sa.Column('hiperparametros', _json(), nullable=False),
        sa.Column('metricas', _json(), nullable=False),
        sa.Column('umbral_probabilidad', sa.Numeric(4, 3), nullable=True),
        sa.Column('cumple_umbrales', sa.Boolean(), nullable=False),
        sa.Column('estado', _enum('estado_version_t'), server_default='candidata', nullable=False),
        sa.Column('mlflow_run_id', sa.String(64), nullable=False),
        sa.Column('ruta_artefacto', sa.Text(), nullable=False),
        sa.Column('sha256_artefacto', sa.CHAR(64), nullable=False),
        sa.Column('sha256_dataset', sa.CHAR(64), nullable=False),
        sa.Column('fecha_registro', tz, server_default=_ahora(), nullable=False),
        sa.Column('fecha_activacion', tz, nullable=True),
        sa.Column('reproducibilidad', _json(), nullable=True),
        sa.PrimaryKeyConstraint('id_version', name='pk_version_modelo'),
        sa.UniqueConstraint('codigo', name='uq_version_modelo_codigo'),
        sa.CheckConstraint('horizonte IN (2, 3, 4)', name=op.f('ck_version_modelo_horizonte_valido')),
        sa.CheckConstraint('umbral_probabilidad BETWEEN 0 AND 1', name=op.f('ck_version_modelo_umbral_valido')),
        sa.CheckConstraint("estado <> 'activa' OR cumple_umbrales",
                           name=op.f('ck_version_modelo_activa_cumple_umbrales')))
    op.create_index('ux_version_activa', 'version_modelo', ['tarea', 'horizonte'], unique=True,
                    postgresql_where=sa.text("estado = 'activa'"), sqlite_where=sa.text("estado = 'activa'"))

    op.create_table('importancia_variable',
        _columna_id('id_importancia', grande=False),
        sa.Column('id_version', sa.Integer(), nullable=False),
        sa.Column('variable', sa.String(100), nullable=False),
        sa.Column('importancia', sa.Numeric(), nullable=False),
        sa.Column('rango', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id_importancia', name='pk_importancia_variable'),
        sa.ForeignKeyConstraint(['id_version'], ['version_modelo.id_version'],
                                name='fk_importancia_variable_id_version_version_modelo'),
        sa.UniqueConstraint('id_version', 'variable', name='uq_importancia_variable_id_version'),
        sa.CheckConstraint('importancia >= 0 AND rango >= 1', name=op.f('ck_importancia_variable_importancia_valida')))

    referencia_ejecucion = sa.BigInteger() if _es_postgresql() else sa.Integer()
    op.create_table('prediccion',
        _columna_id('id_prediccion'),
        sa.Column('ubigeo', sa.CHAR(6), nullable=False),
        sa.Column('id_semana_corte', sa.Integer(), nullable=False),
        sa.Column('id_semana_objetivo', sa.Integer(), nullable=False),
        sa.Column('horizonte', sa.SmallInteger(), nullable=False),
        sa.Column('probabilidad_brote', sa.Numeric(5, 4), nullable=True),
        sa.Column('nivel_riesgo', _enum('nivel_riesgo_t'), nullable=True),
        sa.Column('casos_estimados', sa.Numeric(10, 2), nullable=True),
        sa.Column('estado', _enum('estado_prediccion_t'), nullable=False),
        sa.Column('motivo_no_disponible', sa.Text(), nullable=True),
        sa.Column('id_version_clasificador', sa.Integer(), nullable=True),
        sa.Column('id_version_regresor', sa.Integer(), nullable=True),
        sa.Column('id_ejecucion', referencia_ejecucion, nullable=False),
        sa.Column('fecha_generacion', tz, server_default=_ahora(), nullable=False),
        sa.PrimaryKeyConstraint('id_prediccion', name='pk_prediccion'),
        sa.ForeignKeyConstraint(['ubigeo'], ['distrito.ubigeo'], name='fk_prediccion_ubigeo_distrito'),
        sa.ForeignKeyConstraint(['id_semana_corte'], ['semana_epidemiologica.id_semana'],
                                name='fk_prediccion_id_semana_corte_semana_epidemiologica'),
        sa.ForeignKeyConstraint(['id_semana_objetivo'], ['semana_epidemiologica.id_semana'],
                                name='fk_prediccion_id_semana_objetivo_semana_epidemiologica'),
        sa.ForeignKeyConstraint(['id_version_clasificador'], ['version_modelo.id_version'],
                                name='fk_prediccion_id_version_clasificador_version_modelo'),
        sa.ForeignKeyConstraint(['id_version_regresor'], ['version_modelo.id_version'],
                                name='fk_prediccion_id_version_regresor_version_modelo'),
        sa.ForeignKeyConstraint(['id_ejecucion'], ['ejecucion.id_ejecucion'],
                                name='fk_prediccion_id_ejecucion_ejecucion'),
        sa.UniqueConstraint('ubigeo', 'id_semana_corte', 'horizonte', name='uq_prediccion_ubigeo'),
        sa.CheckConstraint('horizonte IN (2, 3, 4)', name=op.f('ck_prediccion_horizonte_valido')),
        sa.CheckConstraint('probabilidad_brote BETWEEN 0 AND 1', name=op.f('ck_prediccion_probabilidad_valida')),
        sa.CheckConstraint('casos_estimados >= 0', name=op.f('ck_prediccion_casos_no_negativos')),
        sa.CheckConstraint(
            "(estado = 'disponible' AND probabilidad_brote IS NOT NULL AND nivel_riesgo IS NOT NULL)"
            " OR (estado = 'no_disponible' AND probabilidad_brote IS NULL AND nivel_riesgo IS NULL"
            " AND motivo_no_disponible IS NOT NULL)", name=op.f('ck_prediccion_estado_coherente')))
    op.create_index('ix_pred_objetivo', 'prediccion', ['id_semana_objetivo', 'horizonte'])

    op.create_table('alerta',
        _columna_id('id_alerta'),
        sa.Column('id_prediccion', referencia_ejecucion, nullable=False),
        sa.Column('ubigeo', sa.CHAR(6), nullable=False),
        sa.Column('nivel', _enum('nivel_riesgo_t'), nullable=False),
        sa.Column('estado', _enum('estado_alerta_t'), server_default='activa', nullable=False),
        sa.Column('cambio', _enum('cambio_alerta_t'), nullable=False),
        sa.Column('fecha_generacion', tz, server_default=_ahora(), nullable=False),
        sa.Column('fecha_retiro', tz, nullable=True),
        sa.Column('motivo', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id_alerta', name='pk_alerta'),
        sa.ForeignKeyConstraint(['id_prediccion'], ['prediccion.id_prediccion'],
                                name='fk_alerta_id_prediccion_prediccion'),
        sa.ForeignKeyConstraint(['ubigeo'], ['distrito.ubigeo'], name='fk_alerta_ubigeo_distrito'),
        sa.UniqueConstraint('id_prediccion', name='uq_alerta_id_prediccion'),
        sa.CheckConstraint("nivel IN ('alto', 'muy_alto')", name=op.f('ck_alerta_nivel_alerta')),
        sa.CheckConstraint("estado = 'activa' OR fecha_retiro IS NOT NULL", name=op.f('ck_alerta_retiro_con_fecha')))
    op.create_index('ix_alerta_estado', 'alerta', ['estado', 'nivel'])

    parametros = op.create_table('parametro_sistema',
        sa.Column('clave', sa.String(60), nullable=False),
        sa.Column('valor', _json(), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=False),
        sa.Column('fecha_actualizacion', tz, server_default=_ahora(), nullable=False),
        sa.PrimaryKeyConstraint('clave', name='pk_parametro_sistema'))
    return parametros


def _sembrar_parametros():
    """Semillas del DDL como JSON literal, iguales en ambos motores."""
    conversion = '::jsonb' if _es_postgresql() else ''
    for clave, valor, descripcion in PARAMETROS:
        valor_sql = valor.replace("'", "''")
        descripcion_sql = descripcion.replace("'", "''")
        op.execute(f"INSERT INTO parametro_sistema (clave, valor, descripcion) "
                   f"VALUES ('{clave}', '{valor_sql}'{conversion}, '{descripcion_sql}')")


def _seguridad_postgresql():
    """RLS, roles NOLOGIN, permisos (ampliados, decisión f) y políticas de servicio."""
    for tabla in TABLAS_PROTEGIDAS:
        op.execute(f'ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY')
    op.execute("""
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rol_api') THEN
    CREATE ROLE rol_api NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rol_pipeline') THEN
    CREATE ROLE rol_pipeline NOLOGIN;
  END IF;
END $$""")
    op.execute('GRANT SELECT ON ALL TABLES IN SCHEMA public TO rol_api, rol_pipeline')
    op.execute('GRANT INSERT, UPDATE ON prediccion, alerta, ejecucion TO rol_api')
    op.execute('GRANT UPDATE (estado, fecha_activacion) ON version_modelo TO rol_api')
    op.execute('GRANT INSERT, UPDATE ON observacion_semanal, ejecucion, provincia, distrito, '
               'semana_epidemiologica, version_modelo, importancia_variable TO rol_pipeline')
    for tabla in TABLAS_PROTEGIDAS:
        op.execute(f'CREATE POLICY servicio_{tabla} ON {tabla} TO rol_api, rol_pipeline '
                   f'USING (true) WITH CHECK (true)')


def upgrade():
    """Aplica el cambio de esquema."""
    for tabla in TABLAS_ANTERIORES:
        op.drop_table(tabla)
    if _es_postgresql():
        # SQL explícito: también funciona en modo offline (alembic upgrade --sql).
        for nombre, valores in ENUMS.items():
            lista = ', '.join(f"'{v}'" for v in valores)
            op.execute(f'CREATE TYPE {nombre} AS ENUM ({lista})')
    _crear_tablas()
    _sembrar_parametros()
    if _es_postgresql():
        _seguridad_postgresql()


def _revision_anterior(nombre):
    """Carga 0001/0002 para recrear su esquema vacío en el downgrade."""
    archivo = next(Path(__file__).parent.glob(f'{nombre}_*.py'))
    especificacion = spec_from_file_location(f'revision_{nombre}', archivo)
    modulo = module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def downgrade():
    """Vuelve al esquema 0002 vacío; requiere respaldo si existen datos.

    Los roles rol_api y rol_pipeline no se eliminan: son globales del clúster.
    """
    if _es_postgresql():
        op.execute('REVOKE ALL ON alembic_version FROM rol_api, rol_pipeline')
    for tabla in ('alerta', 'prediccion', 'importancia_variable', 'version_modelo',
                  'observacion_semanal', 'ejecucion', 'distrito', 'provincia',
                  'semana_epidemiologica', 'parametro_sistema'):
        op.drop_table(tabla)
    if _es_postgresql():
        for nombre in ENUMS:
            op.execute(f'DROP TYPE {nombre}')
    _revision_anterior('0001_backend').upgrade()
    _revision_anterior('0002_serving').upgrade()
