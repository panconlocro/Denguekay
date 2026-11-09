import { useQuery } from '@tanstack/react-query';
import { allPages, get } from './client';
import type { Alert, District, Observation, Prediction } from './types';

export function useDistricts() {
  return useQuery({
    queryKey: ['districts'],
    queryFn: ({ signal }) =>
      allPages<District>((page) =>
        get('/api/v1/distritos', { pagina: page, tamano_pagina: 100 }, signal),
      ),
  });
}
export function useSummary(horizon: number, enabled: boolean) {
  return useQuery({
    queryKey: ['summary', horizon],
    enabled,
    queryFn: ({ signal }) => get('/api/v1/tablero/resumen', { horizonte: horizon }, signal),
  });
}
export function usePredictions(horizon: number, enabled = true) {
  return useQuery({
    queryKey: ['predictions', horizon],
    enabled,
    queryFn: ({ signal }) =>
      allPages<Prediction>((page) =>
        get(
          '/api/v1/predicciones',
          { horizonte: horizon, pagina: page, tamano_pagina: 100 },
          signal,
        ),
      ),
  });
}
export function useAlerts(horizon: number, enabled = true, state = 'activa') {
  return useQuery({
    queryKey: ['alerts', horizon, state],
    enabled,
    queryFn: ({ signal }) =>
      allPages<Alert>((page) =>
        get(
          '/api/v1/alertas',
          { horizonte: horizon, estado: state, pagina: page, tamano_pagina: 100 },
          signal,
        ),
      ),
  });
}
export function useRiskMap(horizon: number, enabled = true) {
  return useQuery({
    queryKey: ['map', horizon],
    enabled,
    queryFn: ({ signal }) => get('/api/v1/mapa-riesgo', { horizonte: horizon }, signal),
  });
}

export function useDistrictPrediction(ubigeo: string, horizon: number, enabled: boolean) {
  return useQuery({
    queryKey: ['district-prediction', ubigeo, horizon],
    enabled: enabled && !!ubigeo,
    queryFn: ({ signal }) =>
      get('/api/v1/predicciones', { ubigeo, horizonte: horizon, tamano_pagina: 100 }, signal),
  });
}

export function useObservations(ubigeo: string, from?: string, to?: string, enabled = true) {
  return useQuery({
    queryKey: ['observations', ubigeo, from, to],
    enabled: enabled && !!ubigeo && !!from && !!to,
    queryFn: ({ signal }) =>
      allPages<Observation>((page) =>
        get(
          '/api/v1/observaciones',
          {
            ubigeo,
            desde: from,
            hasta: to,
            pagina: page,
            tamano_pagina: 100,
          },
          signal,
        ),
      ),
  });
}

export function useDistrictAlerts(ubigeo: string, horizon: number, enabled: boolean) {
  return useQuery({
    queryKey: ['district-alerts', ubigeo, horizon],
    enabled: enabled && !!ubigeo,
    queryFn: ({ signal }) =>
      allPages<Alert>((page) =>
        get(
          '/api/v1/alertas',
          {
            ubigeo,
            horizonte: horizon,
            estado: 'activa',
            pagina: page,
            tamano_pagina: 100,
          },
          signal,
        ),
      ),
  });
}

export function useAlert(id: number, enabled: boolean) {
  return useQuery({
    queryKey: ['alert-detail', id],
    enabled,
    queryFn: ({ signal }) =>
      get('/api/v1/alertas/{identificador}', {}, signal, { identificador: id }),
  });
}

export function useModels(horizon: number, enabled = true) {
  return useQuery({
    queryKey: ['models', horizon],
    enabled,
    queryFn: ({ signal }) => get('/api/v1/modelos/activo', { horizonte: horizon }, signal),
  });
}

export function useModelDetail(id?: number) {
  return useQuery({
    queryKey: ['model-detail', id],
    enabled: id !== undefined,
    queryFn: async ({ signal }) => {
      const detail = await get('/api/v1/modelos/{identificador}', {}, signal, {
        identificador: id!,
      });
      if (detail.id_version !== id)
        throw new Error('La versión recibida no corresponde a la solicitada.');
      return detail;
    },
  });
}

export function useModelVariables(id?: number) {
  return useQuery({
    queryKey: ['model-variables', id],
    enabled: id !== undefined,
    queryFn: async ({ signal }) => {
      const result = await get('/api/v1/modelos/{identificador}/variables', {}, signal, {
        identificador: id!,
      });
      if (result.id_version !== id)
        throw new Error('Las variables recibidas no corresponden a la versión solicitada.');
      return result;
    },
  });
}
