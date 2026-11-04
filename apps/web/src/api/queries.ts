import { useQuery } from '@tanstack/react-query';
import { allPages, get } from './client';
import type { Alert, District, Prediction } from './types';

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
