import type { components } from './schema';

type Schemas = components['schemas'];
export type Configuration = Schemas['ConfiguracionRespuesta'];
export type District = Schemas['DistritoRespuesta'];
export type Prediction = Schemas['PrediccionRespuesta'];
export type Dashboard = Schemas['TableroRespuesta'];
export type RiskMapData = Schemas['MapaRiesgoRespuesta'];
export type RiskLevel = Schemas['NivelRiesgo']['nivel'];
export type Alert = Schemas['AlertaRespuesta'];
export type Week = Schemas['SemanaRespuesta'];
export type Series = Schemas['SeriesRespuesta'];
export type Model = Schemas['ModeloEnUso'];
export type ModelDetail = Schemas['ModeloDetalle'];
export type Observation = Schemas['ObservacionRespuesta'];
export type Page<T> = {
  disponible: boolean;
  motivo?: string | null;
  fecha_corte_datos: string | null;
  fecha_actualizacion: string | null;
  elementos: T[];
  total: number;
  pagina: number;
  tamano_pagina: number;
};
