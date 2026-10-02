-- Denguekay: esquema del almacén operacional (PostgreSQL / Supabase)
-- Migración 001. Ejecutar como propietario del proyecto.

CREATE TYPE fuente_casos_t      AS ENUM ('excel_historico', 'sala_situacional');
CREATE TYPE cobertura_t         AS ENUM ('verificado', 'sin_registro', 'pendiente');
CREATE TYPE tarea_t             AS ENUM ('clasificacion', 'regresion');
CREATE TYPE estado_version_t    AS ENUM ('candidata', 'activa', 'archivada', 'rechazada');
CREATE TYPE tipo_ejecucion_t    AS ENUM ('ingesta', 'inferencia', 'reentrenamiento', 'mantenimiento');
CREATE TYPE estado_ejecucion_t  AS ENUM ('en_curso', 'exitosa', 'fallida');
CREATE TYPE nivel_riesgo_t      AS ENUM ('bajo', 'medio', 'alto', 'muy_alto');
CREATE TYPE estado_prediccion_t AS ENUM ('disponible', 'no_disponible');
CREATE TYPE estado_alerta_t     AS ENUM ('activa', 'retirada');
CREATE TYPE cambio_alerta_t     AS ENUM ('nueva', 'se_mantiene', 'sube_nivel', 'baja_nivel');

CREATE TABLE provincia (
  ubigeo_provincia char(4) PRIMARY KEY CHECK (ubigeo_provincia ~ '^[0-9]{4}$'),
  nombre           varchar(80) NOT NULL
);

CREATE TABLE distrito (
  ubigeo               char(6) PRIMARY KEY CHECK (ubigeo ~ '^[0-9]{6}$'),
  ubigeo_provincia     char(4) NOT NULL REFERENCES provincia,
  nombre               varchar(80) NOT NULL,
  latitud              numeric(9,6) NOT NULL CHECK (latitud BETWEEN -6.5 AND -3.5),
  longitud             numeric(9,6) NOT NULL CHECK (longitud BETWEEN -81.5 AND -79.0),
  poblacion_censo_2017 integer CHECK (poblacion_censo_2017 > 0),
  activo               boolean NOT NULL DEFAULT true
);

CREATE TABLE semana_epidemiologica (
  id_semana    integer PRIMARY KEY,
  anio         smallint NOT NULL,
  semana       smallint NOT NULL CHECK (semana BETWEEN 1 AND 53),
  fecha_inicio date NOT NULL,
  fecha_fin    date NOT NULL CHECK (fecha_fin = fecha_inicio + 6),
  temporada    smallint NOT NULL,
  UNIQUE (anio, semana)
);

CREATE TABLE ejecucion (
  id_ejecucion    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tipo            tipo_ejecucion_t NOT NULL,
  estado          estado_ejecucion_t NOT NULL DEFAULT 'en_curso',
  id_semana_corte integer REFERENCES semana_epidemiologica,
  inicio          timestamptz NOT NULL DEFAULT now(),
  fin             timestamptz,
  detalle         jsonb,
  mensaje_error   text
);

CREATE TABLE observacion_semanal (
  ubigeo             char(6) NOT NULL REFERENCES distrito,
  id_semana          integer NOT NULL REFERENCES semana_epidemiologica,
  casos_dengue       integer CHECK (casos_dengue >= 0),          -- NULL = sin dato
  umbral_brote_casos numeric(10,2) CHECK (umbral_brote_casos >= 0),
  brote              boolean,
  temp_media_c       numeric(5,2),
  temp_min_c         numeric(5,2),
  temp_max_c         numeric(5,2),
  precip_total_mm    numeric(7,2) CHECK (precip_total_mm BETWEEN 0 AND 1500),
  hum_rel_media_pct  numeric(5,2) CHECK (hum_rel_media_pct BETWEEN 0 AND 100),
  fuente_casos       fuente_casos_t NOT NULL,
  estado_cobertura   cobertura_t NOT NULL,
  fecha_extraccion   timestamptz NOT NULL,
  id_ejecucion       bigint NOT NULL REFERENCES ejecucion,
  PRIMARY KEY (ubigeo, id_semana),
  CHECK (temp_min_c <= temp_media_c AND temp_media_c <= temp_max_c)
);

CREATE TABLE version_modelo (
  id_version          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  codigo              varchar(20) NOT NULL UNIQUE,
  tarea               tarea_t NOT NULL,
  horizonte           smallint NOT NULL CHECK (horizonte IN (2, 3, 4)),
  algoritmo           varchar(40) NOT NULL,
  variables           jsonb NOT NULL,
  hiperparametros     jsonb NOT NULL,
  metricas            jsonb NOT NULL,
  umbral_probabilidad numeric(4,3) CHECK (umbral_probabilidad BETWEEN 0 AND 1),
  cumple_umbrales     boolean NOT NULL,
  estado              estado_version_t NOT NULL DEFAULT 'candidata',
  mlflow_run_id       varchar(64) NOT NULL,
  ruta_artefacto      text NOT NULL,
  sha256_artefacto    char(64) NOT NULL,
  sha256_dataset      char(64) NOT NULL,
  fecha_registro      timestamptz NOT NULL DEFAULT now(),
  fecha_activacion    timestamptz,
  CHECK (estado <> 'activa' OR cumple_umbrales)
);
CREATE UNIQUE INDEX ux_version_activa ON version_modelo (tarea, horizonte) WHERE estado = 'activa';

CREATE TABLE prediccion (
  id_prediccion           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ubigeo                  char(6) NOT NULL REFERENCES distrito,
  id_semana_corte         integer NOT NULL REFERENCES semana_epidemiologica,
  id_semana_objetivo      integer NOT NULL REFERENCES semana_epidemiologica,
  horizonte               smallint NOT NULL CHECK (horizonte IN (2, 3, 4)),
  probabilidad_brote      numeric(5,4) CHECK (probabilidad_brote BETWEEN 0 AND 1),
  nivel_riesgo            nivel_riesgo_t,
  casos_estimados         numeric(10,2) CHECK (casos_estimados >= 0),
  estado                  estado_prediccion_t NOT NULL,
  motivo_no_disponible    text,
  id_version_clasificador integer REFERENCES version_modelo,
  id_version_regresor     integer REFERENCES version_modelo,
  id_ejecucion            bigint NOT NULL REFERENCES ejecucion,
  fecha_generacion        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (ubigeo, id_semana_corte, horizonte),
  CHECK ((estado = 'disponible' AND probabilidad_brote IS NOT NULL AND nivel_riesgo IS NOT NULL)
      OR (estado = 'no_disponible' AND probabilidad_brote IS NULL AND nivel_riesgo IS NULL
          AND motivo_no_disponible IS NOT NULL))
);
CREATE INDEX ix_pred_objetivo ON prediccion (id_semana_objetivo, horizonte);

CREATE TABLE alerta (
  id_alerta        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id_prediccion    bigint NOT NULL UNIQUE REFERENCES prediccion,
  ubigeo           char(6) NOT NULL REFERENCES distrito,
  nivel            nivel_riesgo_t NOT NULL CHECK (nivel IN ('alto', 'muy_alto')),
  estado           estado_alerta_t NOT NULL DEFAULT 'activa',
  cambio           cambio_alerta_t NOT NULL,
  fecha_generacion timestamptz NOT NULL DEFAULT now(),
  fecha_retiro     timestamptz,
  CHECK (estado = 'activa' OR fecha_retiro IS NOT NULL)
);
CREATE INDEX ix_alerta_estado ON alerta (estado, nivel);

CREATE TABLE parametro_sistema (
  clave               varchar(60) PRIMARY KEY,
  valor               jsonb NOT NULL,
  descripcion         text NOT NULL,
  fecha_actualizacion timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_obs_semana ON observacion_semanal (id_semana);
CREATE INDEX ix_ejecucion_tipo_inicio ON ejecucion (tipo, inicio DESC);

-- Parámetros iniciales
INSERT INTO parametro_sistema (clave, valor, descripcion) VALUES
 ('regla_brote', '{"anios_previos": 5, "k_desviaciones": 1.5, "minimo_casos": 2}',
  'Umbral = media de la misma semana en 5 años previos + k DE; mínimo de casos'),
 ('cortes_riesgo', '{"medio": 0.25, "alto": 0.50, "muy_alto": 0.75}',
  'Cortes de probabilidad para el nivel de riesgo'),
 ('umbrales_aceptacion', '{"recall": 0.80, "precision": 0.60, "f1": 0.70, "razon_error_base": 0.85}',
  'Criterios para promover un modelo');

-- Seguridad: RLS activo y sin políticas para anon/authenticated
ALTER TABLE provincia             ENABLE ROW LEVEL SECURITY;
ALTER TABLE distrito              ENABLE ROW LEVEL SECURITY;
ALTER TABLE semana_epidemiologica ENABLE ROW LEVEL SECURITY;
ALTER TABLE observacion_semanal   ENABLE ROW LEVEL SECURITY;
ALTER TABLE version_modelo        ENABLE ROW LEVEL SECURITY;
ALTER TABLE ejecucion             ENABLE ROW LEVEL SECURITY;
ALTER TABLE prediccion            ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerta                ENABLE ROW LEVEL SECURITY;
ALTER TABLE parametro_sistema     ENABLE ROW LEVEL SECURITY;

CREATE ROLE rol_api NOLOGIN;
CREATE ROLE rol_pipeline NOLOGIN;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO rol_api, rol_pipeline;
GRANT INSERT, UPDATE ON prediccion, alerta TO rol_api;
GRANT UPDATE (estado, fecha_activacion) ON version_modelo TO rol_api;
GRANT INSERT, UPDATE ON observacion_semanal, ejecucion TO rol_pipeline;

-- Políticas RLS solo para los roles de servicio
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['provincia','distrito','semana_epidemiologica','observacion_semanal',
                           'version_modelo','ejecucion','prediccion','alerta','parametro_sistema'] LOOP
    EXECUTE format('CREATE POLICY servicio_%s ON %I TO rol_api, rol_pipeline USING (true) WITH CHECK (true)', t, t);
  END LOOP;
END $$;
