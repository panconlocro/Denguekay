import type { Alert, District } from '../api/types';
import { inSelection } from './dashboard';

export type AlertOrder = 'riesgo' | 'probabilidad' | 'fecha';
export function alertFilters(params: URLSearchParams) {
  const state = params.get('aviso_estado') || 'activa';
  const level = params.get('aviso_nivel') || '';
  const order = params.get('aviso_orden') || 'riesgo';
  const week = params.get('aviso_semana') || '';
  const rawPage = params.get('aviso_pagina') || '1';
  const page = Number(rawPage);
  const error =
    !['activa', 'retirada'].includes(state) ||
    !['', 'alto', 'muy_alto'].includes(level) ||
    !['riesgo', 'probabilidad', 'fecha'].includes(order) ||
    (week !== '' && !/^\d{4}(0[1-9]|[1-4]\d|5[0-3])$/.test(week)) ||
    !/^[1-9]\d*$/.test(rawPage) ||
    !Number.isSafeInteger(page);
  return { state: state as Alert['estado'], level, order: order as AlertOrder, week, page, error };
}
export function alertProbability(alert: Alert) {
  return alert.prediccion.disponible && alert.prediccion.estado === 'disponible'
    ? alert.prediccion.probabilidad_brote
    : null;
}
export function alertExperimental(alert: Alert) {
  return alert.experimental || alert.prediccion.experimental;
}
export function sortAlerts(rows: Alert[], order: AlertOrder) {
  const rank = { alto: 1, muy_alto: 2 };
  return [...rows].sort((a, b) => {
    const risk = rank[b.nivel] - rank[a.nivel];
    const probability = (alertProbability(b) ?? -1) - (alertProbability(a) ?? -1);
    const generated = Date.parse(b.fecha_generacion) - Date.parse(a.fecha_generacion);
    return (
      (order === 'fecha'
        ? generated || risk || probability
        : order === 'probabilidad'
          ? probability || risk || generated
          : risk || probability || generated) || b.id_alerta - a.id_alerta
    );
  });
}
export function selectAlerts(
  rows: Alert[],
  state: Alert['estado'],
  horizon: number,
  districts: District[],
  province: string,
  district: string,
  level: string,
  week: string,
) {
  return rows.filter(
    (a) =>
      a.estado === state &&
      a.horizonte === horizon &&
      a.prediccion.horizonte === horizon &&
      a.ubigeo === a.prediccion.ubigeo &&
      inSelection(a.ubigeo, districts, province, district) &&
      (!level || a.nivel === level) &&
      (!week || String(a.prediccion.semana_objetivo.id_semana) === week),
  );
}
export function alertContextSearch(alert: Alert, search: string, districts: District[]) {
  const params = new URLSearchParams(search);
  params.set('horizonte', String(alert.horizonte));
  params.set('distrito', alert.ubigeo);
  params.set('aviso_estado', alert.estado);
  const province = districts.find((d) => d.ubigeo === alert.ubigeo)?.ubigeo_provincia;
  if (province) params.set('provincia', province);
  else params.delete('provincia');
  return `?${params}`;
}
export const alertChanges = {
  nueva: 'Nueva',
  se_mantiene: 'Se mantiene',
  sube_nivel: 'Sube de nivel',
  baja_nivel: 'Baja de nivel',
};
