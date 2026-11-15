"""Disponibilidad de ERA5-Land, CHIRPS y Niño 1+2 para B3."""

from alembic import op
import sqlalchemy as sa

revision = "0008_v4"
down_revision = "0007_v3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("observacion_semanal", sa.Column("casos_solo_confirmados", sa.Boolean(),
                                                   nullable=False, server_default=sa.false()))
    op.add_column("observacion_semanal", sa.Column("humedad_era5_land_pct", sa.Double()))
    op.add_column("observacion_semanal", sa.Column("fecha_era5_land_disponible", sa.Date()))
    op.add_column("observacion_semanal", sa.Column("lluvia_chirps_mm", sa.Double()))
    op.add_column("observacion_semanal", sa.Column("fecha_chirps_disponible", sa.Date()))
    op.create_table(
        "observacion_nino12",
        sa.Column("mes", sa.Date(), primary_key=True),
        sa.Column("fecha_disponible", sa.Date(), nullable=False),
        sa.Column("anomalia", sa.Double(), nullable=False),
    )
    if op.get_context().dialect.name == "postgresql":
        op.execute("ALTER TABLE observacion_nino12 ENABLE ROW LEVEL SECURITY")
        op.execute("GRANT SELECT ON observacion_nino12 TO rol_api, rol_pipeline")
        op.execute("GRANT INSERT, UPDATE ON observacion_nino12 TO rol_pipeline")
        op.execute("CREATE POLICY servicio_observacion_nino12 ON observacion_nino12 "
                   "TO rol_api, rol_pipeline USING (true) WITH CHECK (true)")


def downgrade():
    op.drop_table("observacion_nino12")
    for name in ("fecha_chirps_disponible", "lluvia_chirps_mm", "fecha_era5_land_disponible",
                 "humedad_era5_land_pct", "casos_solo_confirmados"):
        op.drop_column("observacion_semanal", name)
