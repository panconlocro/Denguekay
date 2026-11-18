BEGIN;

-- Running upgrade 0008_v4 -> 0009_v4

UPDATE parametro_sistema SET valor = '{"recall": 0.65, "precision": 0.6, "f1": 0.7, "razon_error_base": 0.9, "bloque": "temporadas_2022_2026"}'::jsonb, fecha_actualizacion = now() WHERE clave = 'umbrales_aceptacion';

UPDATE alembic_version SET version_num='0009_v4' WHERE alembic_version.version_num = '0008_v4';

COMMIT;

