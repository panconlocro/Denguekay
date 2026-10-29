"""Motor de predicción enchufable (fase 3 de docs/backend/prompt_api_v1.md)

Revisión: 0005_v1
Anterior: 0004_v1

Decisiones de docs/backend/api_v1_decisiones.md aprobadas por Rosa:
- C3: dos columnas anulables en prediccion para el intervalo de casos, con un CHECK de coherencia;
  el nivel del intervalo es el parámetro nivel_intervalo_casos (0,80), no una columna (P2 de la fase 3).
- M5: en PostgreSQL, observacion_semanal.hum_rel_media_pct pasa a double precision para que el clima
  de la BD reproduzca el de gold (numeric(5,2) lo redondeaba hasta 0,0043).
- D2: rol_pipeline recibe INSERT y UPDATE en prediccion (predicciones OOS del paquete).

SQLite (solo pruebas): las columnas se agregan con ALTER TABLE ADD COLUMN, que es determinista (el modo
batch recrea la tabla con las restricciones en un orden que cambia entre corridas). SQLite no cambia
tipos de columna, pero tampoco redondea: con afinidad NUMERIC guarda el REAL completo, así que la
humedad conserva su tipo declarado.
"""

from alembic import op
import sqlalchemy as sa


revision = '0005_v1'
down_revision = '0004_v1'
branch_labels = None
depends_on = None

INTERVALO_COHERENTE = (
    "(casos_intervalo_inferior IS NULL AND casos_intervalo_superior IS NULL)"
    " OR (estado = 'disponible' AND casos_intervalo_inferior IS NOT NULL AND casos_intervalo_superior IS NOT NULL"
    " AND casos_intervalo_inferior >= 0 AND casos_intervalo_inferior <= casos_intervalo_superior)")
CK_INTERVALO = 'ck_prediccion_intervalo_coherente'
CLAVE = 'nivel_intervalo_casos'
VALOR = '{"nivel": 0.80}'
DESCRIPCION = ('Probabilidad nominal del intervalo de casos; cada paquete declara su nivel y la '
               'inferencia rechaza uno distinto. Cambiarlo obliga a volver a inferir')


def _es_postgresql():
    return op.get_context().dialect.name == 'postgresql'


def upgrade():
    """Agrega el intervalo, cambia el tipo de la humedad, amplía permisos y siembra el nivel."""
    if _es_postgresql():
        op.add_column('prediccion', sa.Column('casos_intervalo_inferior', sa.Numeric(10, 2), nullable=True))
        op.add_column('prediccion', sa.Column('casos_intervalo_superior', sa.Numeric(10, 2), nullable=True))
        op.create_check_constraint(op.f(CK_INTERVALO), 'prediccion', INTERVALO_COHERENTE)
        op.alter_column('observacion_semanal', 'hum_rel_media_pct', type_=sa.Double(),
                        existing_type=sa.Numeric(5, 2), existing_nullable=True,
                        postgresql_using='hum_rel_media_pct::double precision')
        op.execute('GRANT INSERT, UPDATE ON prediccion TO rol_pipeline')
        conversion = '::jsonb'
    else:
        op.execute('ALTER TABLE prediccion ADD COLUMN casos_intervalo_superior NUMERIC(10, 2)')
        op.execute(f'ALTER TABLE prediccion ADD COLUMN casos_intervalo_inferior NUMERIC(10, 2) '
                   f'CONSTRAINT {CK_INTERVALO} CHECK ({INTERVALO_COHERENTE})')
        conversion = ''
    op.execute(f"INSERT INTO parametro_sistema (clave, valor, descripcion) "
               f"VALUES ('{CLAVE}', '{VALOR}'{conversion}, '{DESCRIPCION}')")


def downgrade():
    """Deshace cada cambio; en PostgreSQL la humedad vuelve a numeric(5,2) redondeada."""
    op.execute(f"DELETE FROM parametro_sistema WHERE clave = '{CLAVE}'")
    if _es_postgresql():
        op.execute('REVOKE INSERT, UPDATE ON prediccion FROM rol_pipeline')
        op.alter_column('observacion_semanal', 'hum_rel_media_pct', type_=sa.Numeric(5, 2),
                        existing_type=sa.Double(), existing_nullable=True,
                        postgresql_using='round(hum_rel_media_pct::numeric, 2)')
        op.drop_constraint(op.f(CK_INTERVALO), 'prediccion', type_='check')
        op.drop_column('prediccion', 'casos_intervalo_superior')
        op.drop_column('prediccion', 'casos_intervalo_inferior')
    else:
        # The inferior column carries the CHECK that references the superior one: it is dropped first.
        op.execute('ALTER TABLE prediccion DROP COLUMN casos_intervalo_inferior')
        op.execute('ALTER TABLE prediccion DROP COLUMN casos_intervalo_superior')
