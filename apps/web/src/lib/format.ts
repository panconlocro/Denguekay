import type { Configuration, Week } from '../api/types';

export function number(value: number | null | undefined, digits = 0) {
  return value == null
    ? 'No disponible'
    : new Intl.NumberFormat('fr-FR', {
        maximumFractionDigits: digits,
      })
        .format(value)
        .replace(/[\u202f\u00a0]/g, ' ');
}
export function percent(value: number | null | undefined) {
  return value == null ? 'Sin datos' : `${number(value * 100, 1)} %`;
}

export function riskRange(from: number | null, to: number | null) {
  if (from == null || to == null) return 'sin predicción válida';
  if (from === 0) return `< ${percent(to)}`;
  if (to === 1) return `≥ ${percent(from)}`;
  return `${percent(from)} – < ${percent(to)}`;
}
export function date(value: string | null | undefined) {
  return value
    ? new Intl.DateTimeFormat('es-PE', {
        timeZone: 'America/Lima',
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
      }).format(new Date(value.length === 10 ? `${value}T12:00:00Z` : value))
    : 'Sin fecha';
}
export function weekLabel(week: Week | null | undefined) {
  return week
    ? `SE ${String(week.semana).padStart(2, '0')} · ${week.anio}`
    : 'Sin semana publicada';
}
export function horizonStatus(h: Configuration['horizontes'][number]) {
  return !h.disponible ? 'No disponible' : h.experimental ? 'Experimental' : 'Operativo';
}
export function targetPassed(week: Week | null | undefined, now = new Date()) {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Lima' }).format(now);
  return !!week && week.fecha_fin < today;
}
