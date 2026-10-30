"""Permiso de rol_pipeline para fijar la selección experimental (fase 4 de docs/backend/prompt_api_v1.md)

Revisión: 0006_v1
Anterior: 0005_v1

Respuesta de Rosa a P4 (docs/backend/api_v1_decisiones.md, «Precisiones de la fase 4»): qué modelo se sirve
es un dato operativo. Lo fija la publicación (``publish --seleccionar-experimental``), no una migración, y
load_data ya no lo siembra. Esta migración no contiene datos de modelos:
- crea la fila seleccion_experimental vacía si no existe (una BD que ya la tenga la conserva);
- en PostgreSQL, rol_pipeline recibe UPDATE de valor y fecha_actualizacion en parametro_sistema, y el RLS lo
  acota a la fila clave = 'seleccion_experimental': la política de servicio de parametro_sistema pasa a ser
  solo de lectura y una política propia permite esa actualización. rol_api sigue sin escribir la tabla.

SQLite (solo pruebas) no tiene roles ni RLS: solo se crea la fila.
"""

from alembic import op


revision = '0006_v1'
down_revision = '0005_v1'
branch_labels = None
depends_on = None

CLAVE = 'seleccion_experimental'
DESCRIPCION = ('Desviación temporal: versiones candidatas que se sirven como experimentales mientras no haya una '
               'versión activa que cumpla los umbrales. La fija la publicación (--seleccionar-experimental)')
POLITICA = 'pipeline_seleccion_experimental'


def _es_postgresql():
    return op.get_context().dialect.name == 'postgresql'


def upgrade():
    """Crea la fila vacía si falta y acota el permiso de rol_pipeline a esa fila."""
    if _es_postgresql():
        op.execute(f"INSERT INTO parametro_sistema (clave, valor, descripcion) "
                   f"VALUES ('{CLAVE}', '{{}}'::jsonb, '{DESCRIPCION}') ON CONFLICT (clave) DO NOTHING")
        op.execute('DROP POLICY servicio_parametro_sistema ON parametro_sistema')
        op.execute('CREATE POLICY servicio_parametro_sistema ON parametro_sistema FOR SELECT '
                   'TO rol_api, rol_pipeline USING (true)')
        op.execute(f"CREATE POLICY {POLITICA} ON parametro_sistema FOR UPDATE TO rol_pipeline "
                   f"USING (clave = '{CLAVE}') WITH CHECK (clave = '{CLAVE}')")
        op.execute('GRANT UPDATE (valor, fecha_actualizacion) ON parametro_sistema TO rol_pipeline')
    else:
        op.execute(f"INSERT OR IGNORE INTO parametro_sistema (clave, valor, descripcion) "
                   f"VALUES ('{CLAVE}', '{{}}', '{DESCRIPCION}')")


def downgrade():
    """Restituye la política de servicio original; la fila solo se borra si sigue vacía."""
    if _es_postgresql():
        op.execute('REVOKE UPDATE (valor, fecha_actualizacion) ON parametro_sistema FROM rol_pipeline')
        op.execute(f'DROP POLICY {POLITICA} ON parametro_sistema')
        op.execute('DROP POLICY servicio_parametro_sistema ON parametro_sistema')
        op.execute('CREATE POLICY servicio_parametro_sistema ON parametro_sistema TO rol_api, rol_pipeline '
                   'USING (true) WITH CHECK (true)')
        op.execute(f"DELETE FROM parametro_sistema WHERE clave = '{CLAVE}' AND valor = '{{}}'::jsonb")
    else:
        op.execute(f"DELETE FROM parametro_sistema WHERE clave = '{CLAVE}' AND valor = '{{}}'")
