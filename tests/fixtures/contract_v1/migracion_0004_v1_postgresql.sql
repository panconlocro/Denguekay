BEGIN;

-- Running upgrade 0003_oe2 -> 0004_v1

INSERT INTO parametro_sistema (clave, valor, descripcion) VALUES ('horizonte_por_defecto', '{"horizonte": 4}'::jsonb, 'Horizonte (semanas) que el frontend muestra por defecto; objetivo de la tesis: 4');

UPDATE alembic_version SET version_num='0004_v1' WHERE alembic_version.version_num = '0003_oe2';

COMMIT;

