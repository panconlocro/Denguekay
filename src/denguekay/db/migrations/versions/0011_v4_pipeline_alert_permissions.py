"""Allow the PostgreSQL pipeline role to create and retire inference alerts."""

from alembic import op

revision = "0011_v4"
down_revision = "0010_v4"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_context().dialect.name == "postgresql":
        op.execute("GRANT INSERT, UPDATE ON alerta TO rol_pipeline")


def downgrade():
    if op.get_context().dialect.name == "postgresql":
        op.execute("REVOKE INSERT, UPDATE ON alerta FROM rol_pipeline")
