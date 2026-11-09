import type { Observation, Series } from '../api/types';
import { intervalText } from './district';
import { weekLabel } from './format';

export const weekMilliseconds = 7 * 86400000;
export function shiftWeeks(day: string, weeks: number) {
  return new Date(Date.parse(`${day}T12:00:00Z`) + weeks * weekMilliseconds)
    .toISOString()
    .slice(0, 10);
}
export function seriesRangeError(from: string, to: string) {
  const valid = (day: string) =>
    /^\d{4}-\d{2}-\d{2}$/.test(day) &&
    Number.isFinite(Date.parse(day)) &&
    new Date(day).toISOString().slice(0, 10) === day;
  if (!valid(from) || !valid(to)) return 'Indica las dos fechas de inicio de semana.';
  if (from > to) return 'La fecha inicial debe ser anterior o igual a la final.';
  if (new Date(from).getUTCDay() !== 0 || new Date(to).getUTCDay() !== 0)
    return 'Selecciona domingos: las fechas corresponden al inicio de cada semana epidemiológica.';
  if (Date.parse(to) - Date.parse(from) > 520 * weekMilliseconds)
    return 'El intervalo no puede superar 520 semanas.';
  return null;
}

export function seriesPoints(series: Series, observations: Observation[] = []) {
  const byWeek = new Map(
    observations.filter((o) => o.ubigeo === series.ubigeo).map((o) => [o.semana.id_semana, o]),
  );
  return series.elementos.map((row) => {
    const p = row.prediccion;
    const prediction =
      p?.disponible &&
      p.estado === 'disponible' &&
      p.ubigeo === series.ubigeo &&
      p.horizonte === series.horizonte &&
      p.semana_objetivo.id_semana === row.semana.id_semana
        ? p
        : undefined;
    const observed = row.observado ? row.casos_dengue : null;
    const afterCut =
      !!series.fecha_corte_datos && row.semana.fecha_inicio > series.fecha_corte_datos;
    return {
      x: Date.parse(`${row.semana.fecha_inicio}T12:00:00Z`),
      label: weekLabel(row.semana),
      start: row.semana.fecha_inicio,
      observed,
      predicted: prediction?.casos_estimados ?? null,
      threshold: byWeek.get(row.semana.id_semana)?.umbral_brote_casos ?? null,
      interval: prediction ? intervalText(prediction) : null,
      origin: !prediction
        ? 'Sin predicción'
        : `${prediction.tipo === 'retrospectiva' ? 'Retrospectiva' : 'Último corte publicado'}${prediction.experimental ? ' · experimental' : ''}`,
      missing: observed == null && !!series.fecha_corte_datos && !afterCut,
      afterCut,
    };
  });
}

export function missingBands(points: ReturnType<typeof seriesPoints>) {
  const bands: { from: number; to: number }[] = [];
  for (const point of points) {
    if (!point.missing) continue;
    const previous = bands[bands.length - 1];
    if (previous && point.x - weekMilliseconds / 2 === previous.to) previous.to += weekMilliseconds;
    else bands.push({ from: point.x - weekMilliseconds / 2, to: point.x + weekMilliseconds / 2 });
  }
  return bands;
}
