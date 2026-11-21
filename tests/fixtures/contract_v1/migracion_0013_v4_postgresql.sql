BEGIN;

-- Running upgrade 0012_v4 -> 0013_v4

CREATE TABLE emision_prediccion (
    ubigeo CHAR(6) NOT NULL, 
    id_semana_corte INTEGER NOT NULL, 
    horizonte SMALLINT NOT NULL, 
    id_semana_objetivo INTEGER NOT NULL, 
    probabilidad_brote NUMERIC(5, 4), 
    nivel_riesgo nivel_riesgo_t, 
    casos_estimados NUMERIC(10, 2), 
    estado estado_prediccion_t NOT NULL, 
    motivo_no_disponible TEXT, 
    id_ejecucion BIGINT NOT NULL, 
    fecha_emision TIMESTAMP WITH TIME ZONE NOT NULL, 
    ultima_semana_sala_publicada INTEGER, 
    procedencia VARCHAR(20) DEFAULT 'emision' NOT NULL, 
    CONSTRAINT pk_emision_prediccion PRIMARY KEY (ubigeo, id_semana_corte, horizonte), 
    CONSTRAINT fk_emision_prediccion_ubigeo_distrito FOREIGN KEY(ubigeo) REFERENCES distrito (ubigeo), 
    CONSTRAINT fk_emision_prediccion_id_semana_corte_semana_epidemiologica FOREIGN KEY(id_semana_corte) REFERENCES semana_epidemiologica (id_semana), 
    CONSTRAINT fk_emision_prediccion_id_semana_objetivo_semana_epidemiologica FOREIGN KEY(id_semana_objetivo) REFERENCES semana_epidemiologica (id_semana), 
    CONSTRAINT fk_emision_prediccion_id_ejecucion_ejecucion FOREIGN KEY(id_ejecucion) REFERENCES ejecucion (id_ejecucion), 
    CONSTRAINT ck_emision_prediccion_horizonte_valido CHECK (horizonte IN (2, 3, 4)), 
    CONSTRAINT ck_emision_prediccion_probabilidad_valida CHECK (probabilidad_brote BETWEEN 0 AND 1), 
    CONSTRAINT ck_emision_prediccion_casos_no_negativos CHECK (casos_estimados >= 0), 
    CONSTRAINT ck_emision_prediccion_estado_coherente CHECK ((estado = 'disponible' AND probabilidad_brote IS NOT NULL AND nivel_riesgo IS NOT NULL) OR (estado = 'no_disponible' AND probabilidad_brote IS NULL AND nivel_riesgo IS NULL AND motivo_no_disponible IS NOT NULL)), 
    CONSTRAINT ck_emision_prediccion_procedencia_valida CHECK (procedencia IN ('emision', 'archivo', 'prediccion_actual'))
);

CREATE INDEX ix_emision_objetivo ON emision_prediccion (id_semana_objetivo, horizonte);

ALTER TABLE emision_prediccion ENABLE ROW LEVEL SECURITY;

GRANT SELECT ON emision_prediccion TO rol_api, rol_pipeline;

GRANT INSERT ON emision_prediccion TO rol_pipeline;

CREATE POLICY lectura_emision_prediccion ON emision_prediccion FOR SELECT TO rol_api, rol_pipeline USING (true);

CREATE POLICY insercion_emision_prediccion ON emision_prediccion FOR INSERT TO rol_pipeline WITH CHECK (true);

UPDATE alembic_version SET version_num='0013_v4' WHERE alembic_version.version_num = '0012_v4';

COMMIT;

