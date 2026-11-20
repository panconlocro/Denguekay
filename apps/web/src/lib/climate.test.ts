import { describe, expect, it } from 'vitest';
import type { Observation } from '../api/types';
import { climateReading } from './climate';

const base: Observation = {
  ubigeo: '200101',
  distrito: 'Piura',
  semana: {
    id_semana: 202644,
    anio: 2026,
    semana: 44,
    fecha_inicio: '2026-10-25',
    fecha_fin: '2026-10-31',
  },
  casos_dengue: 3,
  brote: false,
  umbral_brote_casos: 2,
  temp_media_c: null,
  temp_min_c: null,
  temp_max_c: null,
  precip_total_mm: null,
  hum_rel_media_pct: null,
  fuente_casos: 'sala_situacional',
  estado_cobertura: 'verificado',
};
const lima = (day: string) => new Date(`${day}T17:00:00Z`);

describe('climate of the cutoff week', () => {
  it('prefers the V4 sources and names them', () => {
    const o = {
      ...base,
      temp_media_c: 20,
      temp_media_era5_land_c: 25.5,
      humedad_era5_land_pct: 61.234,
      lluvia_chirps_mm: 3.5,
    };
    expect(climateReading(o, 'temperature')).toEqual({
      status: 'value',
      text: '25,5 °C',
      source: 'ERA5-Land',
    });
    expect(climateReading(o, 'humidity')).toMatchObject({ text: '61,23 %', source: 'ERA5-Land' });
    expect(climateReading(o, 'rain')).toMatchObject({ text: '3,5 mm', source: 'CHIRPS v3' });
  });
  it('falls back to the panel values, also when the API does not send the new fields yet', () => {
    const o = { ...base, temp_media_c: 24, hum_rel_media_pct: 63, precip_total_mm: 0 };
    expect(climateReading(o, 'temperature')).toMatchObject({
      text: '24 °C',
      source: 'Panel Open-Meteo',
    });
    expect(climateReading(o, 'humidity')).toMatchObject({ text: '63 %' });
    // A measured zero is shown as a zero.
    expect(climateReading(o, 'rain')).toMatchObject({ status: 'value', text: '0 mm' });
  });
  it('shows a measured zero of the new source, not the older value', () => {
    const o = { ...base, precip_total_mm: 9, lluvia_chirps_mm: 0 };
    expect(climateReading(o, 'rain')).toMatchObject({ text: '0 mm', source: 'CHIRPS v3' });
  });
  it('reports a missing value as pending until its availability date, and never as 0', () => {
    const o = {
      ...base,
      fecha_era5_land_disponible: '2026-11-10',
      fecha_chirps_disponible: '2026-11-25',
    };
    const today = lima('2026-11-20');
    expect(climateReading(o, 'temperature', today)).toEqual({
      status: 'unavailable',
      text: 'No disponible',
      source: null,
    });
    expect(climateReading(o, 'rain', today)).toEqual({
      status: 'pending',
      text: 'Pendiente de publicación',
      source: null,
    });
    // No availability date: nothing says it was published.
    expect(climateReading(base, 'humidity', today).status).toBe('pending');
    expect(climateReading(o, 'rain', today).text).not.toMatch(/^0/);
  });
  it('uses the Lima calendar day to decide whether the source already published', () => {
    const o = { ...base, fecha_chirps_disponible: '2026-11-20' };
    // 2026-11-19 23:00 in Lima is 04:00 UTC of the 20th; 2026-11-20 02:00 in Lima is 07:00 UTC.
    expect(climateReading(o, 'rain', new Date('2026-11-20T04:00:00Z')).status).toBe('pending');
    expect(climateReading(o, 'rain', new Date('2026-11-20T07:00:00Z')).status).toBe('unavailable');
  });
});
