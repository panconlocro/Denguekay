BEGIN;

-- Running upgrade 0005_v1 -> 0006_v1

INSERT INTO parametro_sistema (clave, valor, descripcion) VALUES ('seleccion_experimental', '{}'::jsonb, 'Desviación temporal: versiones candidatas que se sirven como experimentales mientras no haya una versión activa que cumpla los umbrales. La fija la publicación (--seleccionar-experimental)') ON CONFLICT (clave) DO NOTHING;

DROP POLICY servicio_parametro_sistema ON parametro_sistema;

CREATE POLICY servicio_parametro_sistema ON parametro_sistema FOR SELECT TO rol_api, rol_pipeline USING (true);

CREATE POLICY pipeline_seleccion_experimental ON parametro_sistema FOR UPDATE TO rol_pipeline USING (clave = 'seleccion_experimental') WITH CHECK (clave = 'seleccion_experimental');

GRANT UPDATE (valor, fecha_actualizacion) ON parametro_sistema TO rol_pipeline;

UPDATE alembic_version SET version_num='0006_v1' WHERE alembic_version.version_num = '0005_v1';

COMMIT;

