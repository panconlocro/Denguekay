import { describe, expect, it } from 'vitest';
import type { ModelDetail } from '../api/types';
import { blockLabel, provenanceRows, sharedBoosterNote } from './modelMetrics';

const published = (repro: Record<string, unknown>, block = 'temporada_2025') =>
  ({
    metricas: { bloques: { [block]: { n: 3380 }, temporadas_2022_2026: { n: 16965 } } },
    reproducibilidad: repro,
  }) as unknown as ModelDetail;

describe('temporal protocol of a version', () => {
  it('labels the pooled acceptance block instead of showing its id', () => {
    expect(blockLabel('temporadas_2022_2026')).toBe('Temporadas 2022–2026 (aceptación)');
    expect(blockLabel('temporada_2025')).toBe('Temporada 2025');
    expect(blockLabel('calendario_2025')).toBe('Calendario 2025');
  });
  it('shows the cutoff and target weeks of a block the version publishes', () => {
    const d = published({
      entrenamiento_inicio: '2005-01-02',
      entrenamiento_corte: '2026-10-17',
      filas_entrenamiento: 73775,
      particion_temporal: {
        bloques: {
          temporada_2025: {
            corte_ajuste: '2024-08-03',
            primera_semana_objetivo: '2024-08-25',
            ultima_semana_objetivo: '2025-08-17',
          },
        },
      },
    });
    expect(provenanceRows(d, 'temporada_2025')).toEqual([
      ['Inicio del ajuste de servicio', '02/01/2005'],
      ['Corte del ajuste de servicio', '17/10/2026'],
      ['Filas del ajuste de servicio', '73 775'],
      ['Corte de entrenamiento del bloque', '03/08/2024'],
      ['Primera semana objetivo del bloque', '25/08/2024'],
      ['Última semana objetivo del bloque', '17/08/2025'],
    ]);
  });
  it('leaves out what the version does not publish', () => {
    expect(provenanceRows(published({}), 'temporada_2025')).toEqual([]);
    expect(
      provenanceRows(published({ calibracion: 'Platt por horizonte' }), 'temporada_2025'),
    ).toEqual([['Calibración', 'Platt por horizonte']]);
  });
  it('shows the rule, and the cutoff of each season, when the block has no single cutoff', () => {
    const d = published({
      particion_temporal: {
        bloques: {
          temporadas_2022_2026: {
            corte_ajuste: null,
            regla_ajuste: 'Cada temporada se ajusta una vez, en su primer origen',
            cortes_por_temporada: { '2022': '2021-08-07', '2023': '2022-08-06' },
            primera_semana_objetivo: '2021-08-29',
          },
        },
      },
    });
    const rows = provenanceRows(d, 'temporadas_2022_2026');
    expect(rows).toContainEqual([
      'Regla de ajuste del bloque',
      'Cada temporada se ajusta una vez, en su primer origen',
    ]);
    expect(rows).toContainEqual(['Corte de cada temporada', '2022: 07/08/2021 · 2023: 06/08/2022']);
    expect(rows.map(([label]) => label)).not.toContain('Corte de entrenamiento del bloque');
  });
  it('shows a cutoff published as text as the rule of the block', () => {
    const d = published({
      particion_temporal: {
        bloques: { temporada_2025: { corte_ajuste: 'Primer origen de la temporada' } },
      },
    });
    expect(provenanceRows(d, 'temporada_2025')).toEqual([
      ['Regla de ajuste del bloque', 'Primer origen de la temporada'],
    ]);
  });
  it('does not take the dates of a block the metrics do not publish', () => {
    const d = published({
      particion_temporal: { bloques: { temporada_2018: { corte_ajuste: '2017-08-05' } } },
    });
    expect(provenanceRows(d, 'temporada_2018')).toEqual([]);
  });
  it('reads the shared-booster sentence only when the API publishes it', () => {
    expect(sharedBoosterNote(published({ nota_importancias: 'Comparten booster' }))).toBe(
      'Comparten booster',
    );
    expect(sharedBoosterNote(published({}))).toBeNull();
    expect(sharedBoosterNote(undefined)).toBeNull();
  });
});
