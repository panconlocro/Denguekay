BEGIN;

-- Running upgrade 0010_v4 -> 0011_v4

GRANT INSERT, UPDATE ON alerta TO rol_pipeline;

UPDATE alembic_version SET version_num='0011_v4' WHERE alembic_version.version_num = '0010_v4';

COMMIT;

