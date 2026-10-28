"""${message}

Revisión: ${up_revision}
Anterior: ${down_revision | comma,n}
"""

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade():
    """Aplica el cambio de esquema."""
    ${upgrades if upgrades else "pass"}


def downgrade():
    """Revierte el cambio; requiere respaldo si existen datos."""
    ${downgrades if downgrades else "pass"}
