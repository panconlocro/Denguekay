BEGIN;

-- Running upgrade 0002_serving -> 0003_oe2

DROP TABLE alerta;

DROP TABLE prediccion;

DROP TABLE activacion_modelo;

DROP TABLE importancia_variable;

DROP TABLE observacion_semanal;

DROP TABLE version_modelo;

DROP TABLE ejecucion_prediccion;

DROP TABLE carga_datos;

DROP TABLE distrito;

CREATE TYPE fuente_casos_t AS ENUM ('excel_historico', 'sala_situacional');

CREATE TYPE cobertura_t AS ENUM ('verificado', 'sin_registro', 'pendiente');

CREATE TYPE tarea_t AS ENUM ('clasificacion', 'regresion');

CREATE TYPE estado_version_t AS ENUM ('candidata', 'activa', 'archivada', 'rechazada');

CREATE TYPE tipo_ejecucion_t AS ENUM ('ingesta', 'inferencia', 'reentrenamiento', 'mantenimiento');

CREATE TYPE estado_ejecucion_t AS ENUM ('en_curso', 'exitosa', 'fallida');

CREATE TYPE nivel_riesgo_t AS ENUM ('bajo', 'medio', 'alto', 'muy_alto');

CREATE TYPE estado_prediccion_t AS ENUM ('disponible', 'no_disponible');

CREATE TYPE estado_alerta_t AS ENUM ('activa', 'retirada');

CREATE TYPE cambio_alerta_t AS ENUM ('nueva', 'se_mantiene', 'sube_nivel', 'baja_nivel');

CREATE TABLE provincia (
    ubigeo_provincia CHAR(4) NOT NULL, 
    nombre VARCHAR(80) NOT NULL, 
    CONSTRAINT pk_provincia PRIMARY KEY (ubigeo_provincia), 
    CONSTRAINT ck_provincia_ubigeo_provincia_formato CHECK (ubigeo_provincia ~ '^[0-9]{4}$')
);

CREATE TABLE distrito (
    ubigeo CHAR(6) NOT NULL, 
    ubigeo_provincia CHAR(4) NOT NULL, 
    nombre VARCHAR(80) NOT NULL, 
    latitud NUMERIC(9, 6) NOT NULL, 
    longitud NUMERIC(9, 6) NOT NULL, 
    poblacion_censo_2017 INTEGER, 
    activo BOOLEAN DEFAULT true NOT NULL, 
    CONSTRAINT pk_distrito PRIMARY KEY (ubigeo), 
    CONSTRAINT fk_distrito_ubigeo_provincia_provincia FOREIGN KEY(ubigeo_provincia) REFERENCES provincia (ubigeo_provincia), 
    CONSTRAINT ck_distrito_ubigeo_formato CHECK (ubigeo ~ '^[0-9]{6}$'), 
    CONSTRAINT ck_distrito_latitud_piura CHECK (latitud BETWEEN -6.5 AND -3.5), 
    CONSTRAINT ck_distrito_longitud_piura CHECK (longitud BETWEEN -81.5 AND -79.0), 
    CONSTRAINT ck_distrito_poblacion_positiva CHECK (poblacion_censo_2017 > 0)
);

CREATE TABLE semana_epidemiologica (
    id_semana INTEGER NOT NULL, 
    anio SMALLINT NOT NULL, 
    semana SMALLINT NOT NULL, 
    fecha_inicio DATE NOT NULL, 
    fecha_fin DATE NOT NULL, 
    temporada SMALLINT NOT NULL, 
    CONSTRAINT pk_semana_epidemiologica PRIMARY KEY (id_semana), 
    CONSTRAINT uq_semana_epidemiologica_anio UNIQUE (anio, semana), 
    CONSTRAINT ck_semana_epidemiologica_semana_valida CHECK (semana BETWEEN 1 AND 53), 
    CONSTRAINT ck_semana_epidemiologica_fecha_fin_valida CHECK (fecha_fin = fecha_inicio + 6)
);

CREATE TABLE ejecucion (
    id_ejecucion BIGINT GENERATED ALWAYS AS IDENTITY, 
    tipo tipo_ejecucion_t NOT NULL, 
    estado estado_ejecucion_t DEFAULT 'en_curso' NOT NULL, 
    id_semana_corte INTEGER, 
    inicio TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    fin TIMESTAMP WITH TIME ZONE, 
    detalle JSONB, 
    mensaje_error TEXT, 
    CONSTRAINT pk_ejecucion PRIMARY KEY (id_ejecucion), 
    CONSTRAINT fk_ejecucion_id_semana_corte_semana_epidemiologica FOREIGN KEY(id_semana_corte) REFERENCES semana_epidemiologica (id_semana)
);

CREATE INDEX ix_ejecucion_tipo_inicio ON ejecucion (tipo, inicio DESC);

CREATE UNIQUE INDEX ux_ejecucion_huella_ingesta ON ejecucion ((detalle ->> 'huella')) WHERE tipo = 'ingesta' AND estado = 'exitosa';

CREATE TABLE observacion_semanal (
    ubigeo CHAR(6) NOT NULL, 
    id_semana INTEGER NOT NULL, 
    casos_dengue INTEGER, 
    umbral_brote_casos NUMERIC(10, 2), 
    brote BOOLEAN, 
    temp_media_c NUMERIC(5, 2), 
    temp_min_c NUMERIC(5, 2), 
    temp_max_c NUMERIC(5, 2), 
    precip_total_mm NUMERIC(7, 2), 
    hum_rel_media_pct NUMERIC(5, 2), 
    fuente_casos fuente_casos_t NOT NULL, 
    estado_cobertura cobertura_t NOT NULL, 
    fecha_extraccion TIMESTAMP WITH TIME ZONE NOT NULL, 
    id_ejecucion BIGINT NOT NULL, 
    CONSTRAINT pk_observacion_semanal PRIMARY KEY (ubigeo, id_semana), 
    CONSTRAINT fk_observacion_semanal_ubigeo_distrito FOREIGN KEY(ubigeo) REFERENCES distrito (ubigeo), 
    CONSTRAINT fk_observacion_semanal_id_semana_semana_epidemiologica FOREIGN KEY(id_semana) REFERENCES semana_epidemiologica (id_semana), 
    CONSTRAINT fk_observacion_semanal_id_ejecucion_ejecucion FOREIGN KEY(id_ejecucion) REFERENCES ejecucion (id_ejecucion), 
    CONSTRAINT ck_observacion_semanal_casos_no_negativos CHECK (casos_dengue >= 0), 
    CONSTRAINT ck_observacion_semanal_umbral_no_negativo CHECK (umbral_brote_casos >= 0), 
    CONSTRAINT ck_observacion_semanal_precipitacion_valida CHECK (precip_total_mm BETWEEN 0 AND 1500), 
    CONSTRAINT ck_observacion_semanal_humedad_valida CHECK (hum_rel_media_pct BETWEEN 0 AND 100), 
    CONSTRAINT ck_observacion_semanal_temperaturas_ordenadas CHECK (temp_min_c <= temp_media_c AND temp_media_c <= temp_max_c)
);

CREATE INDEX ix_obs_semana ON observacion_semanal (id_semana);

CREATE TABLE version_modelo (
    id_version INTEGER GENERATED ALWAYS AS IDENTITY, 
    codigo VARCHAR(20) NOT NULL, 
    tarea tarea_t NOT NULL, 
    horizonte SMALLINT NOT NULL, 
    algoritmo VARCHAR(40) NOT NULL, 
    variables JSONB NOT NULL, 
    hiperparametros JSONB NOT NULL, 
    metricas JSONB NOT NULL, 
    umbral_probabilidad NUMERIC(4, 3), 
    cumple_umbrales BOOLEAN NOT NULL, 
    estado estado_version_t DEFAULT 'candidata' NOT NULL, 
    mlflow_run_id VARCHAR(64) NOT NULL, 
    ruta_artefacto TEXT NOT NULL, 
    sha256_artefacto CHAR(64) NOT NULL, 
    sha256_dataset CHAR(64) NOT NULL, 
    fecha_registro TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    fecha_activacion TIMESTAMP WITH TIME ZONE, 
    reproducibilidad JSONB, 
    CONSTRAINT pk_version_modelo PRIMARY KEY (id_version), 
    CONSTRAINT uq_version_modelo_codigo UNIQUE (codigo), 
    CONSTRAINT ck_version_modelo_horizonte_valido CHECK (horizonte IN (2, 3, 4)), 
    CONSTRAINT ck_version_modelo_umbral_valido CHECK (umbral_probabilidad BETWEEN 0 AND 1), 
    CONSTRAINT ck_version_modelo_activa_cumple_umbrales CHECK (estado <> 'activa' OR cumple_umbrales)
);

CREATE UNIQUE INDEX ux_version_activa ON version_modelo (tarea, horizonte) WHERE estado = 'activa';

CREATE TABLE importancia_variable (
    id_importancia INTEGER GENERATED ALWAYS AS IDENTITY, 
    id_version INTEGER NOT NULL, 
    variable VARCHAR(100) NOT NULL, 
    importancia NUMERIC NOT NULL, 
    rango INTEGER NOT NULL, 
    CONSTRAINT pk_importancia_variable PRIMARY KEY (id_importancia), 
    CONSTRAINT fk_importancia_variable_id_version_version_modelo FOREIGN KEY(id_version) REFERENCES version_modelo (id_version), 
    CONSTRAINT uq_importancia_variable_id_version UNIQUE (id_version, variable), 
    CONSTRAINT ck_importancia_variable_importancia_valida CHECK (importancia >= 0 AND rango >= 1)
);

CREATE TABLE prediccion (
    id_prediccion BIGINT GENERATED ALWAYS AS IDENTITY, 
    ubigeo CHAR(6) NOT NULL, 
    id_semana_corte INTEGER NOT NULL, 
    id_semana_objetivo INTEGER NOT NULL, 
    horizonte SMALLINT NOT NULL, 
    probabilidad_brote NUMERIC(5, 4), 
    nivel_riesgo nivel_riesgo_t, 
    casos_estimados NUMERIC(10, 2), 
    estado estado_prediccion_t NOT NULL, 
    motivo_no_disponible TEXT, 
    id_version_clasificador INTEGER, 
    id_version_regresor INTEGER, 
    id_ejecucion BIGINT NOT NULL, 
    fecha_generacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_prediccion PRIMARY KEY (id_prediccion), 
    CONSTRAINT fk_prediccion_ubigeo_distrito FOREIGN KEY(ubigeo) REFERENCES distrito (ubigeo), 
    CONSTRAINT fk_prediccion_id_semana_corte_semana_epidemiologica FOREIGN KEY(id_semana_corte) REFERENCES semana_epidemiologica (id_semana), 
    CONSTRAINT fk_prediccion_id_semana_objetivo_semana_epidemiologica FOREIGN KEY(id_semana_objetivo) REFERENCES semana_epidemiologica (id_semana), 
    CONSTRAINT fk_prediccion_id_version_clasificador_version_modelo FOREIGN KEY(id_version_clasificador) REFERENCES version_modelo (id_version), 
    CONSTRAINT fk_prediccion_id_version_regresor_version_modelo FOREIGN KEY(id_version_regresor) REFERENCES version_modelo (id_version), 
    CONSTRAINT fk_prediccion_id_ejecucion_ejecucion FOREIGN KEY(id_ejecucion) REFERENCES ejecucion (id_ejecucion), 
    CONSTRAINT uq_prediccion_ubigeo UNIQUE (ubigeo, id_semana_corte, horizonte), 
    CONSTRAINT ck_prediccion_horizonte_valido CHECK (horizonte IN (2, 3, 4)), 
    CONSTRAINT ck_prediccion_probabilidad_valida CHECK (probabilidad_brote BETWEEN 0 AND 1), 
    CONSTRAINT ck_prediccion_casos_no_negativos CHECK (casos_estimados >= 0), 
    CONSTRAINT ck_prediccion_estado_coherente CHECK ((estado = 'disponible' AND probabilidad_brote IS NOT NULL AND nivel_riesgo IS NOT NULL) OR (estado = 'no_disponible' AND probabilidad_brote IS NULL AND nivel_riesgo IS NULL AND motivo_no_disponible IS NOT NULL))
);

CREATE INDEX ix_pred_objetivo ON prediccion (id_semana_objetivo, horizonte);

CREATE TABLE alerta (
    id_alerta BIGINT GENERATED ALWAYS AS IDENTITY, 
    id_prediccion BIGINT NOT NULL, 
    ubigeo CHAR(6) NOT NULL, 
    nivel nivel_riesgo_t NOT NULL, 
    estado estado_alerta_t DEFAULT 'activa' NOT NULL, 
    cambio cambio_alerta_t NOT NULL, 
    fecha_generacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    fecha_retiro TIMESTAMP WITH TIME ZONE, 
    motivo TEXT, 
    CONSTRAINT pk_alerta PRIMARY KEY (id_alerta), 
    CONSTRAINT fk_alerta_id_prediccion_prediccion FOREIGN KEY(id_prediccion) REFERENCES prediccion (id_prediccion), 
    CONSTRAINT fk_alerta_ubigeo_distrito FOREIGN KEY(ubigeo) REFERENCES distrito (ubigeo), 
    CONSTRAINT uq_alerta_id_prediccion UNIQUE (id_prediccion), 
    CONSTRAINT ck_alerta_nivel_alerta CHECK (nivel IN ('alto', 'muy_alto')), 
    CONSTRAINT ck_alerta_retiro_con_fecha CHECK (estado = 'activa' OR fecha_retiro IS NOT NULL)
);

CREATE INDEX ix_alerta_estado ON alerta (estado, nivel);

CREATE TABLE parametro_sistema (
    clave VARCHAR(60) NOT NULL, 
    valor JSONB NOT NULL, 
    descripcion TEXT NOT NULL, 
    fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_parametro_sistema PRIMARY KEY (clave)
);

INSERT INTO parametro_sistema (clave, valor, descripcion) VALUES ('regla_brote', '{"anios_previos": 5, "k_desviaciones": 1.5, "minimo_casos": 2}'::jsonb, 'Umbral = media de la misma semana en 5 años previos + k DE; mínimo de casos');

INSERT INTO parametro_sistema (clave, valor, descripcion) VALUES ('cortes_riesgo', '{"medio": 0.25, "alto": 0.50, "muy_alto": 0.75}'::jsonb, 'Cortes de probabilidad para el nivel de riesgo');

INSERT INTO parametro_sistema (clave, valor, descripcion) VALUES ('umbrales_aceptacion', '{"recall": 0.80, "precision": 0.60, "f1": 0.70, "razon_error_base": 0.85, "bloque": "temporada_2024"}'::jsonb, 'Criterios para promover un modelo');

ALTER TABLE provincia ENABLE ROW LEVEL SECURITY;

ALTER TABLE distrito ENABLE ROW LEVEL SECURITY;

ALTER TABLE semana_epidemiologica ENABLE ROW LEVEL SECURITY;

ALTER TABLE observacion_semanal ENABLE ROW LEVEL SECURITY;

ALTER TABLE version_modelo ENABLE ROW LEVEL SECURITY;

ALTER TABLE ejecucion ENABLE ROW LEVEL SECURITY;

ALTER TABLE prediccion ENABLE ROW LEVEL SECURITY;

ALTER TABLE alerta ENABLE ROW LEVEL SECURITY;

ALTER TABLE parametro_sistema ENABLE ROW LEVEL SECURITY;

ALTER TABLE importancia_variable ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rol_api') THEN
    CREATE ROLE rol_api NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rol_pipeline') THEN
    CREATE ROLE rol_pipeline NOLOGIN;
  END IF;
END $$;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO rol_api, rol_pipeline;

GRANT INSERT, UPDATE ON prediccion, alerta, ejecucion TO rol_api;

GRANT UPDATE (estado, fecha_activacion) ON version_modelo TO rol_api;

GRANT INSERT, UPDATE ON observacion_semanal, ejecucion, provincia, distrito, semana_epidemiologica, version_modelo, importancia_variable TO rol_pipeline;

CREATE POLICY servicio_provincia ON provincia TO rol_api, rol_pipeline USING (true) WITH CHECK (true);

CREATE POLICY servicio_distrito ON distrito TO rol_api, rol_pipeline USING (true) WITH CHECK (true);

CREATE POLICY servicio_semana_epidemiologica ON semana_epidemiologica TO rol_api, rol_pipeline USING (true) WITH CHECK (true);

CREATE POLICY servicio_observacion_semanal ON observacion_semanal TO rol_api, rol_pipeline USING (true) WITH CHECK (true);

CREATE POLICY servicio_version_modelo ON version_modelo TO rol_api, rol_pipeline USING (true) WITH CHECK (true);

CREATE POLICY servicio_ejecucion ON ejecucion TO rol_api, rol_pipeline USING (true) WITH CHECK (true);

CREATE POLICY servicio_prediccion ON prediccion TO rol_api, rol_pipeline USING (true) WITH CHECK (true);

CREATE POLICY servicio_alerta ON alerta TO rol_api, rol_pipeline USING (true) WITH CHECK (true);

CREATE POLICY servicio_parametro_sistema ON parametro_sistema TO rol_api, rol_pipeline USING (true) WITH CHECK (true);

CREATE POLICY servicio_importancia_variable ON importancia_variable TO rol_api, rol_pipeline USING (true) WITH CHECK (true);

UPDATE alembic_version SET version_num='0003_oe2' WHERE alembic_version.version_num = '0002_serving';

COMMIT;

