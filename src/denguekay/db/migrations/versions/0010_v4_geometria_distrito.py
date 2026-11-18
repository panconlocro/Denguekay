"""Geometría de cada distrito para el mapa de riesgo (HU0014-1)

Revisión: 0010_v4
Anterior: 0009_v4

Agrega ``distrito.geometria`` (Polygon o MultiPolygon de GeoJSON, anulable): la carga la llena desde los límites
distritales versionados (COD-AB de Perú, IGN, publicados por OCHA en HDX, CC BY-IGO 3.0). Si falta, ``/mapa-riesgo``
responde con el centroide, como hasta ahora. Es una extensión del esquema del documento OE2 (ver
docs/backend/desviaciones_oe2.md).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_v4"
down_revision = "0009_v4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("distrito", sa.Column(
        "geometria", sa.JSON(none_as_null=True).with_variant(postgresql.JSONB(none_as_null=True), "postgresql"),
        nullable=True))


def downgrade():
    op.drop_column("distrito", "geometria")
