import { describe, expect, it } from 'vitest';
import type { ModelDetail } from '../api/types';
import { baselineRatio, blockIds, importances, metrics } from './modelMetrics';

function detail(block: Record<string, unknown>, id = 'calendario_2025') {
  return { metricas: { bloques: { [id]: block } } } as unknown as ModelDetail;
}

describe('published model metrics', () => {
  it('reads v0 and v2 AUPRC locations without replacing zero or explicit null', () => {
    expect(
      metrics(
        detail({ clasificacion: { alerta_directa: { recall: 0, auprc: 0.3 } } }),
        'calendario_2025',
      ),
    ).toMatchObject({ recall: 0, auprc: 0.3 });
    expect(
      metrics(
        detail({ clasificacion: { auprc: null, alerta_directa: { auprc: 0.3 } } }),
        'calendario_2025',
      ).auprc,
    ).toBeNull();
    expect(
      metrics(
        detail({ clasificacion: { auprc: 0, alerta_directa: { recall: '0.8', f1: NaN } } }),
        'calendario_2025',
      ),
    ).toMatchObject({ auprc: 0, recall: null, f1: null });
  });
  it('never substitutes a different block or task for missing metrics', () => {
    const d = detail({ regresion: { conteos: { mae: 3 } }, persistencia: { conteos: { mae: 4 } } });
    expect(metrics(d, 'temporada_2024')).toMatchObject({ available: false, mae: null });
    expect(metrics(d, 'calendario_2025')).toMatchObject({
      available: true,
      mae: 3,
      baselineMae: 4,
      recall: null,
    });
  });
  it('defaults to the latest dated published block without averaging', () => {
    expect(
      blockIds(
        detail({}, 'temporada_2023'),
        detail({}, 'calendario_2025'),
        detail({}, 'temporada_2024'),
      ),
    ).toEqual(['calendario_2025', 'temporada_2024', 'temporada_2023']);
  });
  it('keeps undefined ratios distinct from a zero model error', () => {
    expect(baselineRatio(0, 4)).toBe(0);
    expect(baselineRatio(0, 0)).toBeNull();
    expect(baselineRatio(4, null)).toBeNull();
    expect(baselineRatio(5, 4)).toBe(125);
  });
  it('preserves raw importance magnitudes and filters malformed entries', () => {
    expect(
      importances([
        { variable: 'x', importancia: 12.8, rango: 2 },
        { variable: 'y', importancia: 0, rango: 1 },
        { variable: 'z', importancia: '4', rango: 3 },
        { variable: 'a', importancia: -2, rango: 4 },
      ]),
    ).toEqual([
      { variable: 'y', importance: 0, rank: 1 },
      { variable: 'x', importance: 12.8, rank: 2 },
    ]);
  });
});
