import { describe, expect, it } from 'vitest';
import type { Dashboard, Prediction } from '../api/types';
import {
  consistentPredictions,
  emissionTiming,
  regionalForecast,
  sortPredictions,
} from './dashboard';

const cut = {
  id_semana: 202552,
  anio: 2025,
  semana: 52,
  fecha_inicio: '2025-12-21',
  fecha_fin: '2025-12-27',
};
const target = {
  id_semana: 202601,
  anio: 2026,
  semana: 1,
  fecha_inicio: '2026-01-04',
  fecha_fin: '2026-01-10',
};
function prediction(overrides: Partial<Prediction> = {}): Prediction {
  return {
    id_prediccion: 1,
    ubigeo: '200101',
    distrito: 'Piura',
    horizonte: 2,
    semana_corte: cut,
    semana_objetivo: target,
    tipo: 'vigente',
    estado: 'disponible',
    disponible: true,
    motivo: null,
    probabilidad_brote: 0,
    nivel_riesgo: 'bajo',
    nivel_riesgo_etiqueta: 'Bajo',
    casos_estimados: 0,
    casos_intervalo_inferior: null,
    casos_intervalo_superior: null,
    nivel_intervalo: null,
    motivo_intervalo: 'Sin intervalo',
    casos_persistencia: 0,
    alerta_modelo: false,
    experimental: true,
    id_version_clasificador: 1,
    id_version_regresor: 2,
    id_ejecucion: 1,
    fecha_generacion: '2025-12-21T05:00:00Z',
    ...overrides,
  };
}
const summary: Dashboard = {
  disponible: true,
  motivo: null,
  fecha_corte_datos: '2025-12-27',
  fecha_actualizacion: '2026-11-04T23:00:00Z',
  horizonte: 2,
  semana_corte: cut,
  semana_objetivo: target,
  experimental: true,
  distritos: 2,
  distritos_con_prediccion: 2,
  niveles_riesgo: { bajo: 2, medio: 0, alto: 0, muy_alto: 0 },
  alertas_activas: 0,
  casos_estimados_region: { disponible: true, valor: 0, motivo: null },
  casos_observados_ultima_semana: { disponible: true, valor: 0, motivo: null },
  nota: 'Prueba unitaria',
};
const rows = [prediction(), prediction({ ubigeo: '200104', distrito: 'Castilla' })];

describe('regional forecast coverage', () => {
  it('preserves a complete regional zero without estimating a new total', () => {
    expect(regionalForecast(summary, rows).value).toBe(0);
    expect(
      regionalForecast(
        { ...summary, casos_estimados_region: { disponible: true, valor: 1.23 } },
        rows,
      ).value,
    ).toBe(1.23);
  });
  it('withholds aggregates marked available when a magnitude or district is missing', () => {
    expect(regionalForecast(summary, [rows[0]]).value).toBeNull();
    expect(
      regionalForecast(summary, [rows[0], prediction({ ubigeo: '200104', casos_estimados: null })])
        .value,
    ).toBeNull();
    expect(regionalForecast(summary, [rows[0], rows[0]]).value).toBeNull();
    expect(regionalForecast(summary).value).toBeNull();
  });
  it('never combines snapshots from different targets or horizons', () => {
    expect(consistentPredictions([rows[0], prediction({ horizonte: 4 })], 2)).toBe(false);
    const other = { ...target, id_semana: 202602 };
    expect(regionalForecast({ ...summary, semana_objetivo: other }, rows).value).toBeNull();
    expect(
      regionalForecast(summary, [rows[0], prediction({ semana_objetivo: other })]).value,
    ).toBeNull();
  });
});

describe('publication timing and priority', () => {
  it('uses actual emission timestamps and midnight in Piura for the minimum effective lead', () => {
    expect(emissionTiming(rows)?.minimumWeeks).toBe(2);
    const late = prediction({ fecha_generacion: '2025-12-21T05:00:01Z' });
    expect(emissionTiming([...rows, late])!.minimumWeeks).toBeLessThan(2);
    expect(
      emissionTiming([prediction({ fecha_generacion: summary.fecha_actualizacion! })])!
        .minimumWeeks,
    ).toBeLessThan(0);
  });
  it('keeps missing timing unavailable and excludes unavailable predictions', () => {
    expect(emissionTiming([prediction({ fecha_generacion: 'invalid' })])).toBeNull();
    expect(emissionTiming([prediction({ disponible: false })])).toBeNull();
  });
  it('places zero probabilities before nulls and breaks ties by UBIGEO', () => {
    const input = [prediction({ ubigeo: '200106', probabilidad_brote: null }), ...rows].reverse();
    const original = [...input];
    expect(sortPredictions(input).map((p) => p.ubigeo)).toEqual(['200101', '200104', '200106']);
    expect(input).toEqual(original);
  });
});
