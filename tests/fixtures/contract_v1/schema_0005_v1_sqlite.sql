-- alembic_version: 0005_v1
-- index ix_alerta_estado ON alerta
CREATE INDEX ix_alerta_estado ON alerta (estado, nivel);

-- index ix_ejecucion_tipo_inicio ON ejecucion
CREATE INDEX ix_ejecucion_tipo_inicio ON ejecucion (tipo, inicio DESC);

-- index ix_obs_semana ON observacion_semanal
CREATE INDEX ix_obs_semana ON observacion_semanal (id_semana);

-- index ix_pred_objetivo ON prediccion
CREATE INDEX ix_pred_objetivo ON prediccion (id_semana_objetivo, horizonte);

-- index ux_version_activa ON version_modelo
CREATE UNIQUE INDEX ux_version_activa ON version_modelo (tarea, horizonte) WHERE estado = 'activa';

-- table alembic_version ON alembic_version
CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL, 
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- table alerta ON alerta
CREATE TABLE alerta (
	id_alerta INTEGER NOT NULL, 
	id_prediccion INTEGER NOT NULL, 
	ubigeo CHAR(6) NOT NULL, 
	nivel VARCHAR(8) NOT NULL, 
	estado VARCHAR(8) DEFAULT 'activa' NOT NULL, 
	cambio VARCHAR(11) NOT NULL, 
	fecha_generacion DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	fecha_retiro DATETIME, 
	motivo TEXT, 
	CONSTRAINT pk_alerta PRIMARY KEY (id_alerta), 
	CONSTRAINT fk_alerta_id_prediccion_prediccion FOREIGN KEY(id_prediccion) REFERENCES prediccion (id_prediccion), 
	CONSTRAINT fk_alerta_ubigeo_distrito FOREIGN KEY(ubigeo) REFERENCES distrito (ubigeo), 
	CONSTRAINT uq_alerta_id_prediccion UNIQUE (id_prediccion), 
	CONSTRAINT ck_alerta_nivel_alerta CHECK (nivel IN ('alto', 'muy_alto')), 
	CONSTRAINT ck_alerta_retiro_con_fecha CHECK (estado = 'activa' OR fecha_retiro IS NOT NULL), 
	CONSTRAINT ck_alerta_nivel_riesgo_t CHECK (nivel IN ('bajo', 'medio', 'alto', 'muy_alto')), 
	CONSTRAINT ck_alerta_estado_alerta_t CHECK (estado IN ('activa', 'retirada')), 
	CONSTRAINT ck_alerta_cambio_alerta_t CHECK (cambio IN ('nueva', 'se_mantiene', 'sube_nivel', 'baja_nivel'))
);

-- table distrito ON distrito
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
	CONSTRAINT ck_distrito_ubigeo_formato CHECK (length(ubigeo) = 6 AND substr(ubigeo, 1, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 2, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 3, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 4, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 5, 1) BETWEEN '0' AND '9' AND substr(ubigeo, 6, 1) BETWEEN '0' AND '9'), 
	CONSTRAINT ck_distrito_latitud_piura CHECK (latitud BETWEEN -6.5 AND -3.5), 
	CONSTRAINT ck_distrito_longitud_piura CHECK (longitud BETWEEN -81.5 AND -79.0), 
	CONSTRAINT ck_distrito_poblacion_positiva CHECK (poblacion_censo_2017 > 0)
);

-- table ejecucion ON ejecucion
CREATE TABLE ejecucion (
	id_ejecucion INTEGER NOT NULL, 
	tipo VARCHAR(15) NOT NULL, 
	estado VARCHAR(8) DEFAULT 'en_curso' NOT NULL, 
	id_semana_corte INTEGER, 
	inicio DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	fin DATETIME, 
	detalle JSON, 
	mensaje_error TEXT, 
	CONSTRAINT pk_ejecucion PRIMARY KEY (id_ejecucion), 
	CONSTRAINT fk_ejecucion_id_semana_corte_semana_epidemiologica FOREIGN KEY(id_semana_corte) REFERENCES semana_epidemiologica (id_semana), 
	CONSTRAINT ck_ejecucion_tipo_ejecucion_t CHECK (tipo IN ('ingesta', 'inferencia', 'reentrenamiento', 'mantenimiento')), 
	CONSTRAINT ck_ejecucion_estado_ejecucion_t CHECK (estado IN ('en_curso', 'exitosa', 'fallida'))
);

-- table importancia_variable ON importancia_variable
CREATE TABLE importancia_variable (
	id_importancia INTEGER NOT NULL, 
	id_version INTEGER NOT NULL, 
	variable VARCHAR(100) NOT NULL, 
	importancia NUMERIC NOT NULL, 
	rango INTEGER NOT NULL, 
	CONSTRAINT pk_importancia_variable PRIMARY KEY (id_importancia), 
	CONSTRAINT fk_importancia_variable_id_version_version_modelo FOREIGN KEY(id_version) REFERENCES version_modelo (id_version), 
	CONSTRAINT uq_importancia_variable_id_version UNIQUE (id_version, variable), 
	CONSTRAINT ck_importancia_variable_importancia_valida CHECK (importancia >= 0 AND rango >= 1)
);

-- table observacion_semanal ON observacion_semanal
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
	fuente_casos VARCHAR(16) NOT NULL, 
	estado_cobertura VARCHAR(12) NOT NULL, 
	fecha_extraccion DATETIME NOT NULL, 
	id_ejecucion INTEGER NOT NULL, 
	CONSTRAINT pk_observacion_semanal PRIMARY KEY (ubigeo, id_semana), 
	CONSTRAINT fk_observacion_semanal_ubigeo_distrito FOREIGN KEY(ubigeo) REFERENCES distrito (ubigeo), 
	CONSTRAINT fk_observacion_semanal_id_semana_semana_epidemiologica FOREIGN KEY(id_semana) REFERENCES semana_epidemiologica (id_semana), 
	CONSTRAINT fk_observacion_semanal_id_ejecucion_ejecucion FOREIGN KEY(id_ejecucion) REFERENCES ejecucion (id_ejecucion), 
	CONSTRAINT ck_observacion_semanal_casos_no_negativos CHECK (casos_dengue >= 0), 
	CONSTRAINT ck_observacion_semanal_umbral_no_negativo CHECK (umbral_brote_casos >= 0), 
	CONSTRAINT ck_observacion_semanal_precipitacion_valida CHECK (precip_total_mm BETWEEN 0 AND 1500), 
	CONSTRAINT ck_observacion_semanal_humedad_valida CHECK (hum_rel_media_pct BETWEEN 0 AND 100), 
	CONSTRAINT ck_observacion_semanal_temperaturas_ordenadas CHECK (temp_min_c <= temp_media_c AND temp_media_c <= temp_max_c), 
	CONSTRAINT ck_observacion_semanal_fuente_casos_t CHECK (fuente_casos IN ('excel_historico', 'sala_situacional')), 
	CONSTRAINT ck_observacion_semanal_cobertura_t CHECK (estado_cobertura IN ('verificado', 'sin_registro', 'pendiente'))
);

-- table parametro_sistema ON parametro_sistema
CREATE TABLE parametro_sistema (
	clave VARCHAR(60) NOT NULL, 
	valor JSON NOT NULL, 
	descripcion TEXT NOT NULL, 
	fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_parametro_sistema PRIMARY KEY (clave)
);

-- table prediccion ON prediccion
CREATE TABLE prediccion (
	id_prediccion INTEGER NOT NULL, 
	ubigeo CHAR(6) NOT NULL, 
	id_semana_corte INTEGER NOT NULL, 
	id_semana_objetivo INTEGER NOT NULL, 
	horizonte SMALLINT NOT NULL, 
	probabilidad_brote NUMERIC(5, 4), 
	nivel_riesgo VARCHAR(8), 
	casos_estimados NUMERIC(10, 2), 
	estado VARCHAR(13) NOT NULL, 
	motivo_no_disponible TEXT, 
	id_version_clasificador INTEGER, 
	id_version_regresor INTEGER, 
	id_ejecucion INTEGER NOT NULL, 
	fecha_generacion DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, casos_intervalo_superior NUMERIC(10, 2), casos_intervalo_inferior NUMERIC(10, 2) CONSTRAINT ck_prediccion_intervalo_coherente CHECK ((casos_intervalo_inferior IS NULL AND casos_intervalo_superior IS NULL) OR (estado = 'disponible' AND casos_intervalo_inferior IS NOT NULL AND casos_intervalo_superior IS NOT NULL AND casos_intervalo_inferior >= 0 AND casos_intervalo_inferior <= casos_intervalo_superior)), 
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
	CONSTRAINT ck_prediccion_estado_coherente CHECK ((estado = 'disponible' AND probabilidad_brote IS NOT NULL AND nivel_riesgo IS NOT NULL) OR (estado = 'no_disponible' AND probabilidad_brote IS NULL AND nivel_riesgo IS NULL AND motivo_no_disponible IS NOT NULL)), 
	CONSTRAINT ck_prediccion_nivel_riesgo_t CHECK (nivel_riesgo IN ('bajo', 'medio', 'alto', 'muy_alto')), 
	CONSTRAINT ck_prediccion_estado_prediccion_t CHECK (estado IN ('disponible', 'no_disponible'))
);

-- table provincia ON provincia
CREATE TABLE provincia (
	ubigeo_provincia CHAR(4) NOT NULL, 
	nombre VARCHAR(80) NOT NULL, 
	CONSTRAINT pk_provincia PRIMARY KEY (ubigeo_provincia), 
	CONSTRAINT ck_provincia_ubigeo_provincia_formato CHECK (length(ubigeo_provincia) = 4 AND substr(ubigeo_provincia, 1, 1) BETWEEN '0' AND '9' AND substr(ubigeo_provincia, 2, 1) BETWEEN '0' AND '9' AND substr(ubigeo_provincia, 3, 1) BETWEEN '0' AND '9' AND substr(ubigeo_provincia, 4, 1) BETWEEN '0' AND '9')
);

-- table semana_epidemiologica ON semana_epidemiologica
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
	CONSTRAINT ck_semana_epidemiologica_fecha_fin_valida CHECK (fecha_fin = date(fecha_inicio, '+6 days'))
);

-- table version_modelo ON version_modelo
CREATE TABLE version_modelo (
	id_version INTEGER NOT NULL, 
	codigo VARCHAR(20) NOT NULL, 
	tarea VARCHAR(13) NOT NULL, 
	horizonte SMALLINT NOT NULL, 
	algoritmo VARCHAR(40) NOT NULL, 
	variables JSON NOT NULL, 
	hiperparametros JSON NOT NULL, 
	metricas JSON NOT NULL, 
	umbral_probabilidad NUMERIC(4, 3), 
	cumple_umbrales BOOLEAN NOT NULL, 
	estado VARCHAR(9) DEFAULT 'candidata' NOT NULL, 
	mlflow_run_id VARCHAR(64) NOT NULL, 
	ruta_artefacto TEXT NOT NULL, 
	sha256_artefacto CHAR(64) NOT NULL, 
	sha256_dataset CHAR(64) NOT NULL, 
	fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	fecha_activacion DATETIME, 
	reproducibilidad JSON, 
	CONSTRAINT pk_version_modelo PRIMARY KEY (id_version), 
	CONSTRAINT uq_version_modelo_codigo UNIQUE (codigo), 
	CONSTRAINT ck_version_modelo_horizonte_valido CHECK (horizonte IN (2, 3, 4)), 
	CONSTRAINT ck_version_modelo_umbral_valido CHECK (umbral_probabilidad BETWEEN 0 AND 1), 
	CONSTRAINT ck_version_modelo_activa_cumple_umbrales CHECK (estado <> 'activa' OR cumple_umbrales), 
	CONSTRAINT ck_version_modelo_tarea_t CHECK (tarea IN ('clasificacion', 'regresion')), 
	CONSTRAINT ck_version_modelo_estado_version_t CHECK (estado IN ('candidata', 'activa', 'archivada', 'rechazada'))
);
