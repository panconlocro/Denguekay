"""Tabla de solo inserción con la primera emisión de cada pronóstico (auditoría del 20/11/2026)

Revisión: 0013_v4
Anterior: 0012_v4

``prediccion`` se sobrescribe cuando se reemite un corte (UPSERT), de modo que la evaluación prospectiva y la revisión
de deriva no podían saber qué se pronosticó la primera vez. ``emision_prediccion`` guarda la primera emisión de cada
(distrito, corte, horizonte) de la actualización semanal y nunca se modifica: es elegible para la evaluación la que, al
emitirse, tenía la semana objetivo todavía sin publicar en la Sala (``id_semana_objetivo`` posterior a
``ultima_semana_sala_publicada``). Desviación registrada en docs/backend/desviaciones_oe2.md.

PostgreSQL: RLS como el resto de las tablas; ``rol_pipeline`` solo inserta y ``rol_api`` y ``rol_pipeline`` leen; ningún
rol recibe UPDATE ni DELETE. SQLite (solo pruebas): sin roles.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013_v4"
down_revision = "0012_v4"
branch_labels = None
depends_on = None

TABLE = "emision_prediccion"
RISK = ("bajo", "medio", "alto", "muy_alto")
STATUS = ("disponible", "no_disponible")


def _postgresql():
    return op.get_context().dialect.name == "postgresql"


def _enum(name, values):
    if _postgresql():
        return postgresql.ENUM(*values, name=name, create_type=False)
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade():
    execution_id = sa.BigInteger() if _postgresql() else sa.Integer()
    op.create_table(
        TABLE,
        sa.Column("ubigeo", sa.CHAR(6), nullable=False),
        sa.Column("id_semana_corte", sa.Integer(), nullable=False),
        sa.Column("horizonte", sa.SmallInteger(), nullable=False),
        sa.Column("id_semana_objetivo", sa.Integer(), nullable=False),
        sa.Column("probabilidad_brote", sa.Numeric(5, 4), nullable=True),
        sa.Column("nivel_riesgo", _enum("nivel_riesgo_t", RISK), nullable=True),
        sa.Column("casos_estimados", sa.Numeric(10, 2), nullable=True),
        sa.Column("estado", _enum("estado_prediccion_t", STATUS), nullable=False),
        sa.Column("motivo_no_disponible", sa.Text(), nullable=True),
        sa.Column("id_ejecucion", execution_id, nullable=False),
        sa.Column("fecha_emision", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ultima_semana_sala_publicada", sa.Integer(), nullable=True),
        sa.Column("procedencia", sa.String(20), server_default="emision", nullable=False),
        sa.PrimaryKeyConstraint("ubigeo", "id_semana_corte", "horizonte", name="pk_emision_prediccion"),
        sa.ForeignKeyConstraint(["ubigeo"], ["distrito.ubigeo"], name="fk_emision_prediccion_ubigeo_distrito"),
        sa.ForeignKeyConstraint(["id_semana_corte"], ["semana_epidemiologica.id_semana"],
                                name="fk_emision_prediccion_id_semana_corte_semana_epidemiologica"),
        sa.ForeignKeyConstraint(["id_semana_objetivo"], ["semana_epidemiologica.id_semana"],
                                name="fk_emision_prediccion_id_semana_objetivo_semana_epidemiologica"),
        sa.ForeignKeyConstraint(["id_ejecucion"], ["ejecucion.id_ejecucion"],
                                name="fk_emision_prediccion_id_ejecucion_ejecucion"),
        sa.CheckConstraint("horizonte IN (2, 3, 4)", name=op.f("ck_emision_prediccion_horizonte_valido")),
        sa.CheckConstraint("probabilidad_brote BETWEEN 0 AND 1",
                           name=op.f("ck_emision_prediccion_probabilidad_valida")),
        sa.CheckConstraint("casos_estimados >= 0", name=op.f("ck_emision_prediccion_casos_no_negativos")),
        sa.CheckConstraint(
            "(estado = 'disponible' AND probabilidad_brote IS NOT NULL AND nivel_riesgo IS NOT NULL)"
            " OR (estado = 'no_disponible' AND probabilidad_brote IS NULL AND nivel_riesgo IS NULL"
            " AND motivo_no_disponible IS NOT NULL)", name=op.f("ck_emision_prediccion_estado_coherente")),
        sa.CheckConstraint("procedencia IN ('emision', 'archivo', 'prediccion_actual')",
                           name=op.f("ck_emision_prediccion_procedencia_valida")),
    )
    op.create_index("ix_emision_objetivo", TABLE, ["id_semana_objetivo", "horizonte"])
    if _postgresql():
        op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
        op.execute(f"GRANT SELECT ON {TABLE} TO rol_api, rol_pipeline")
        op.execute(f"GRANT INSERT ON {TABLE} TO rol_pipeline")
        op.execute(f"CREATE POLICY lectura_{TABLE} ON {TABLE} FOR SELECT TO rol_api, rol_pipeline USING (true)")
        op.execute(f"CREATE POLICY insercion_{TABLE} ON {TABLE} FOR INSERT TO rol_pipeline WITH CHECK (true)")


def downgrade():
    op.drop_table(TABLE)
