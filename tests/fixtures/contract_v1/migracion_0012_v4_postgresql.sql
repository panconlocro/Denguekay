BEGIN;

-- Running upgrade 0011_v4 -> 0012_v4

ALTER TYPE fuente_casos_t ADD VALUE IF NOT EXISTS 'datos_abiertos_confirmados' AFTER 'excel_historico';

UPDATE alembic_version SET version_num='0012_v4' WHERE alembic_version.version_num = '0011_v4';

COMMIT;

