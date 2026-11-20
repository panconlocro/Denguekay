import type { Observation } from '../api/types';
import { limaToday, number } from './format';

export type ClimateKind = 'temperature' | 'humidity' | 'rain';
export type ClimateReading = {
  status: 'value' | 'pending' | 'unavailable';
  text: string;
  source: string | null;
};

type Field = keyof Observation;
// Since contract 1.2.0 the API also publishes the climate the V4 uses (ERA5-Land and CHIRPS v3). Those values come
// first; the legacy panel fields (Open-Meteo, which ends in 2025) are the fallback, and a frontend deployed before
// the API simply finds the new fields undefined.
const KINDS: Record<
  ClimateKind,
  { primary: Field; fallback: Field; available: Field; unit: string; source: string }
> = {
  temperature: {
    primary: 'temp_media_era5_land_c',
    fallback: 'temp_media_c',
    available: 'fecha_era5_land_disponible',
    unit: '°C',
    source: 'ERA5-Land',
  },
  humidity: {
    primary: 'humedad_era5_land_pct',
    fallback: 'hum_rel_media_pct',
    available: 'fecha_era5_land_disponible',
    unit: '%',
    source: 'ERA5-Land',
  },
  rain: {
    primary: 'lluvia_chirps_mm',
    fallback: 'precip_total_mm',
    available: 'fecha_chirps_disponible',
    unit: 'mm',
    source: 'CHIRPS v3',
  },
};
export const LEGACY_SOURCE = 'Panel Open-Meteo';

function numeric(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function climateReading(
  observation: Observation,
  kind: ClimateKind,
  now = new Date(),
): ClimateReading {
  const spec = KINDS[kind];
  const primary = numeric(observation[spec.primary]);
  const fallback = numeric(observation[spec.fallback]);
  const value = primary ?? fallback;
  // A zero is a measurement: only a missing value is reported as missing, and never as 0.
  if (value !== null)
    return {
      status: 'value',
      text: `${number(value, 2)} ${spec.unit}`,
      source: primary !== null ? spec.source : LEGACY_SOURCE,
    };
  const availableFrom = observation[spec.available];
  const published = typeof availableFrom === 'string' && availableFrom <= limaToday(now);
  return published
    ? { status: 'unavailable', text: 'No disponible', source: null }
    : { status: 'pending', text: 'Pendiente de publicación', source: null };
}
