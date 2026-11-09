"""Temperatura de ERA5-Land para servir la v3 (decisión de Rosa del 2026-11-09, desviación OE2)

Revisión: 0007_v3
Anterior: 0006_v1

La v3 (CONFIG_V3) usa cuatro ventanas de la temperatura media semanal de ERA5-Land (d3). La temperatura que ya
guarda observacion_semanal (temp_media_c) es la de Open-Meteo sin modelo fijado y la sigue usando lo demás: no
se toca. Se agrega una columna anulable aparte, temp_media_era5_land_c:
- double precision, para que la BD reproduzca el silver semanal (media de 7 valores diarios) sin redondear;
- CHECK de rango físico (−20 a 50 °C);
- la llena load_data desde el silver de ERA5-Land; NULL = sin dato (la inferencia de la v3 la exige en las 13
  semanas hasta el origen).
Los permisos de la tabla no cambian (rol_api lee y rol_pipeline escribe la tabla entera).

SQLite (solo pruebas): ALTER TABLE ADD COLUMN, determinista; con afinidad NUMERIC guarda el REAL completo.
Desviación registrada en docs/backend/desviaciones_oe2.md, sección 9.
"""

from alembic import op
import sqlalchemy as sa


revision = '0007_v3'
down_revision = '0006_v1'
branch_labels = None
depends_on = None

COLUMNA = 'temp_media_era5_land_c'
CK = 'ck_observacion_semanal_temperatura_era5_land_valida'
RANGO = f'{COLUMNA} BETWEEN -20 AND 50'


def _es_postgresql():
    return op.get_context().dialect.name == 'postgresql'


def upgrade():
    """Agrega la columna con su CHECK."""
    if _es_postgresql():
        op.add_column('observacion_semanal', sa.Column(COLUMNA, sa.Double(), nullable=True))
        op.create_check_constraint(op.f(CK), 'observacion_semanal', RANGO)
    else:
        op.execute(f'ALTER TABLE observacion_semanal ADD COLUMN {COLUMNA} NUMERIC CONSTRAINT {CK} CHECK ({RANGO})')


def downgrade():
    """Quita la columna (y su CHECK)."""
    if _es_postgresql():
        op.drop_constraint(op.f(CK), 'observacion_semanal', type_='check')
        op.drop_column('observacion_semanal', COLUMNA)
    else:
        op.execute(f'ALTER TABLE observacion_semanal DROP COLUMN {COLUMNA}')
