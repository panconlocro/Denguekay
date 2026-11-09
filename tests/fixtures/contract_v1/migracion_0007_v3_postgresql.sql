BEGIN;

-- Running upgrade 0006_v1 -> 0007_v3

ALTER TABLE observacion_semanal ADD COLUMN temp_media_era5_land_c DOUBLE PRECISION;

ALTER TABLE observacion_semanal ADD CONSTRAINT ck_observacion_semanal_temperatura_era5_land_valida CHECK (temp_media_era5_land_c BETWEEN -20 AND 50);

UPDATE alembic_version SET version_num='0007_v3' WHERE alembic_version.version_num = '0006_v1';

COMMIT;

