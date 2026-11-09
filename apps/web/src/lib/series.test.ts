import { describe, expect, it } from 'vitest';
import type { Observation, Prediction, Series } from '../api/types';
import { missingBands, seriesPoints, seriesRangeError, shiftWeeks } from './series';

const first = {
  id_semana: 202552,
  anio: 2025,
  semana: 52,
  fecha_inicio: '2025-12-21',
  fecha_fin: '2025-12-27',
};
const second = {
  ...first,
  id_semana: 202553,
  semana: 53,
  fecha_inicio: '2025-12-28',
  fecha_fin: '2026-01-03',
};
const third = {
  ...first,
  id_semana: 202601,
  anio: 2026,
  semana: 1,
  fecha_inicio: '2026-01-04',
  fecha_fin: '2026-01-10',
};
const prediction: Prediction = {
  id_prediccion: 1,
  ubigeo: '200101',
  distrito: 'Piura',
  horizonte: 2,
  semana_corte: first,
  semana_objetivo: third,
  tipo: 'vigente',
  estado: 'disponible',
  disponible: true,
  motivo: null,
  probabilidad_brote: 0,
  nivel_riesgo: 'bajo',
  nivel_riesgo_etiqueta: 'Bajo',
  casos_estimados: 0.37,
  casos_intervalo_inferior: 0,
  casos_intervalo_superior: 1,
  nivel_intervalo: 0.8,
  motivo_intervalo: null,
  casos_persistencia: 0,
  alerta_modelo: false,
  experimental: true,
  id_version_clasificador: 1,
  id_version_regresor: 2,
  id_ejecucion: 1,
  fecha_generacion: '2026-11-04T23:00:00Z',
};
const series: Series = {
  disponible: true,
  motivo: null,
  fecha_corte_datos: '2025-12-27',
  fecha_actualizacion: '2026-11-04T23:00:00Z',
  ubigeo: '200101',
  distrito: 'Piura',
  horizonte: 2,
  desde: first.fecha_inicio,
  hasta: third.fecha_inicio,
  elementos: [
    { semana: first, observado: true, casos_dengue: 0, brote: false, prediccion: null },
    { semana: second, observado: false, casos_dengue: null, brote: null, prediccion: null },
    { semana: third, observado: false, casos_dengue: null, brote: null, prediccion: prediction },
  ],
};
const observation: Observation = {
  ubigeo: '200101',
  distrito: 'Piura',
  semana: first,
  casos_dengue: 0,
  brote: false,
  umbral_brote_casos: 12.96,
  temp_media_c: 24,
  temp_min_c: 19,
  temp_max_c: 34,
  precip_total_mm: 0,
  hum_rel_media_pct: 63,
  fuente_casos: 'sala_situacional',
  estado_cobertura: 'verificado',
};

describe('weekly series integrity', () => {
  it('keeps zero observed, missing observations and a singleton published forecast distinct', () => {
    const points = seriesPoints(series, [observation]);
    expect(points.map((p) => p.observed)).toEqual([0, null, null]);
    expect(points.map((p) => p.predicted)).toEqual([null, null, 0.37]);
    expect(points[2].origin).toContain('Último corte publicado · experimental');
    expect(points[2].interval).toBe('0 – 1 casos · intervalo nominal 80 %');
  });
  it('aligns historical thresholds by district and week without carrying them into future targets', () => {
    const points = seriesPoints(series, [
      observation,
      { ...observation, ubigeo: '200104', semana: third, umbral_brote_casos: 99 },
    ]);
    expect(points.map((p) => p.threshold)).toEqual([12.96, null, null]);
  });
  it('does not plot a prediction from another horizon, target or unavailable state', () => {
    for (const bad of [
      { ...prediction, horizonte: 4 },
      { ...prediction, semana_objetivo: first },
      { ...prediction, disponible: false },
    ]) {
      const modified = {
        ...series,
        elementos: [...series.elementos.slice(0, 2), { ...series.elementos[2], prediccion: bad }],
      };
      expect(seriesPoints(modified)[2].predicted).toBeNull();
    }
  });
  it('shades missing historical weeks without labelling post-cut weeks as missing observations', () => {
    const modified = {
      ...series,
      elementos: [{ ...series.elementos[0], casos_dengue: null }, ...series.elementos.slice(1)],
    };
    const points = seriesPoints(modified);
    expect(points.map((p) => p.missing)).toEqual([true, false, false]);
    expect(missingBands(points)).toHaveLength(1);
  });
});

describe('weekly range validation', () => {
  it('calculates 52 inclusive weekly points across a year boundary', () => {
    expect(shiftWeeks('2026-01-04', -51)).toBe('2025-01-12');
    expect(seriesRangeError('2025-01-12', '2026-01-04')).toBeNull();
  });
  it('rejects missing, reversed, non-weekly and oversized ranges before a request', () => {
    expect(seriesRangeError('', '2026-01-04')).not.toBeNull();
    expect(seriesRangeError('2026-01-04', '2025-12-21')).not.toBeNull();
    expect(seriesRangeError('2025-12-22', '2026-01-04')).not.toBeNull();
    expect(seriesRangeError('2025-02-30', '2026-01-04')).not.toBeNull();
    expect(seriesRangeError('2010-01-03', '2026-01-04')).not.toBeNull();
  });
});
