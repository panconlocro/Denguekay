BEGIN;

-- Running upgrade 0007_v3 -> 0008_v4

ALTER TABLE observacion_semanal ADD COLUMN casos_solo_confirmados BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE observacion_semanal ADD COLUMN humedad_era5_land_pct DOUBLE PRECISION;

ALTER TABLE observacion_semanal ADD COLUMN fecha_era5_land_disponible DATE;

ALTER TABLE observacion_semanal ADD COLUMN lluvia_chirps_mm DOUBLE PRECISION;

ALTER TABLE observacion_semanal ADD COLUMN fecha_chirps_disponible DATE;

CREATE TABLE observacion_nino12 (
    mes DATE NOT NULL, 
    fecha_disponible DATE NOT NULL, 
    anomalia DOUBLE PRECISION NOT NULL, 
    CONSTRAINT pk_observacion_nino12 PRIMARY KEY (mes)
);

ALTER TABLE observacion_nino12 ENABLE ROW LEVEL SECURITY;

GRANT SELECT ON observacion_nino12 TO rol_api, rol_pipeline;

GRANT INSERT, UPDATE ON observacion_nino12 TO rol_pipeline;

CREATE POLICY servicio_observacion_nino12 ON observacion_nino12 TO rol_api, rol_pipeline USING (true) WITH CHECK (true);

UPDATE alembic_version SET version_num='0008_v4' WHERE alembic_version.version_num = '0007_v3';

COMMIT;

