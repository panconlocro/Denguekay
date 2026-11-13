import { describe, expect, it } from 'vitest';
import type { RiskMapData } from '../api/types';
import { districtPath, intervalText, mapCounts } from './district';

describe('district presentation', () => {
  it('preserves zero bounds and refuses incomplete or inverted intervals', () => {
    const interval = {
      casos_intervalo_inferior: 0,
      casos_intervalo_superior: 1,
      nivel_intervalo: 0.8,
    };
    expect(intervalText(interval)).toBe('0 – 1 casos · intervalo nominal 80 %');
    expect(intervalText({ ...interval, casos_intervalo_superior: null })).toBeNull();
    expect(intervalText({ ...interval, casos_intervalo_inferior: 2 })).toBeNull();
    expect(intervalText({ ...interval, nivel_intervalo: null })).toBeNull();
  });
  it('normalizes district links while preserving the selected series range', () => {
    const path = districtPath(
      '/alertas',
      '?distrito=999999&provincia=9999&seleccion=999999&serie_ventana=52',
      '200101',
      '2001',
      3,
    );
    const url = new URL(path, 'http://localhost');
    expect(url.searchParams.get('distrito')).toBe('200101');
    expect(url.searchParams.get('provincia')).toBe('2001');
    expect(url.searchParams.get('horizonte')).toBe('3');
    expect(url.searchParams.get('serie_ventana')).toBe('52');
    expect(url.searchParams.has('seleccion')).toBe(false);
  });
  it('counts an unavailable feature as missing even if it carries an old risk level', () => {
    const data = {
      leyenda: [
        { nivel: 'bajo', etiqueta: 'Bajo', desde: 0, hasta: 0.25 },
        { nivel: null, etiqueta: 'Sin datos', desde: null, hasta: null },
      ],
      features: [
        { properties: { estado: 'disponible', nivel_riesgo: 'bajo' } },
        { properties: { estado: 'no_disponible', nivel_riesgo: 'bajo' } },
      ],
    } as RiskMapData;
    expect(mapCounts(data).map((level) => level.count)).toEqual([1, 1]);
  });
});
