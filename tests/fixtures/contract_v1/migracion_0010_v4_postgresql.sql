BEGIN;

-- Running upgrade 0009_v4 -> 0010_v4

ALTER TABLE distrito ADD COLUMN geometria JSONB;

UPDATE alembic_version SET version_num='0010_v4' WHERE alembic_version.version_num = '0009_v4';

COMMIT;

