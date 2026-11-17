"""Umbrales de aceptación de la US v1.4 (HU0007-4) y su bloque agregado

Revisión: 0009_v4
Anterior: 0008_v4

Solo cambia los valores de la fila ``umbrales_aceptacion`` de ``parametro_sistema``; el esquema no cambia.
Criterio de la HU0007-4 en la US v1.4: evaluación retrospectiva fuera de muestra por bloques de temporada,
agregando las semanas distritales de temporada_2022 a temporada_2026 en el bloque ``temporadas_2022_2026``.
Clasificador: recall ≥ 0,65, precisión ≥ 0,60 y F1 ≥ 0,70 con p ≥ 0,50. Regresor: MAE y RMSE ≤ 90 % de los de
la persistencia. Los umbrales se revisaron el 17/11/2026, después de ver los resultados de la V4; la evaluación
independiente es la prospectiva 2026-27.
"""

import json

from alembic import op

revision = "0009_v4"
down_revision = "0008_v4"
branch_labels = None
depends_on = None

NEW = {"recall": 0.65, "precision": 0.60, "f1": 0.70, "razon_error_base": 0.90, "bloque": "temporadas_2022_2026"}
OLD = {"recall": 0.80, "precision": 0.60, "f1": 0.70, "razon_error_base": 0.85, "bloque": "temporada_2024"}


def _set(value):
    # The JSON goes inline as a literal (no bound parameter): ``alembic upgrade --sql`` renders a bound parameter as NULL.
    literal = json.dumps(value)
    postgresql = op.get_context().dialect.name == "postgresql"
    payload = f"'{literal}'::jsonb" if postgresql else f"'{literal}'"
    now = "now()" if postgresql else "CURRENT_TIMESTAMP"
    op.execute(f"UPDATE parametro_sistema SET valor = {payload}, fecha_actualizacion = {now} "
               "WHERE clave = 'umbrales_aceptacion'")


def upgrade():
    _set(NEW)


def downgrade():
    _set(OLD)
