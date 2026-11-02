BEGIN;

-- Running upgrade 0004_v1 -> 0005_v1

ALTER TABLE prediccion ADD COLUMN casos_intervalo_inferior NUMERIC(10, 2);

ALTER TABLE prediccion ADD COLUMN casos_intervalo_superior NUMERIC(10, 2);

ALTER TABLE prediccion ADD CONSTRAINT ck_prediccion_intervalo_coherente CHECK ((casos_intervalo_inferior IS NULL AND casos_intervalo_superior IS NULL) OR (estado = 'disponible' AND casos_intervalo_inferior IS NOT NULL AND casos_intervalo_superior IS NOT NULL AND casos_intervalo_inferior >= 0 AND casos_intervalo_inferior <= casos_intervalo_superior));

ALTER TABLE observacion_semanal ALTER COLUMN hum_rel_media_pct TYPE DOUBLE PRECISION USING hum_rel_media_pct::double precision;

GRANT INSERT, UPDATE ON prediccion TO rol_pipeline;

INSERT INTO parametro_sistema (clave, valor, descripcion) VALUES ('nivel_intervalo_casos', '{"nivel": 0.80}'::jsonb, 'Probabilidad nominal del intervalo de casos; cada paquete declara su nivel y la inferencia rechaza uno distinto. Cambiarlo obliga a volver a inferir');

UPDATE alembic_version SET version_num='0005_v1' WHERE alembic_version.version_num = '0004_v1';

COMMIT;

