import type { Prediction, RiskMapData } from '../api/types';
import { number, percent } from './format';

type Interval = Pick<
  Prediction,
  'casos_intervalo_inferior' | 'casos_intervalo_superior' | 'nivel_intervalo'
>;

export function intervalText(value: Interval) {
  const {
    casos_intervalo_inferior: lower,
    casos_intervalo_superior: upper,
    nivel_intervalo: level,
  } = value;
  return lower != null &&
    upper != null &&
    level != null &&
    lower >= 0 &&
    upper >= lower &&
    level > 0 &&
    level < 1
    ? `${number(lower, 2)} – ${number(upper, 2)} casos · intervalo nominal ${percent(level)}`
    : null;
}

export function districtPath(
  path: string,
  search: string,
  ubigeo: string,
  province: string,
  horizon: number,
) {
  const params = new URLSearchParams(search);
  params.set('distrito', ubigeo);
  params.set('provincia', province);
  params.set('horizonte', String(horizon));
  params.delete('seleccion');
  return `${path}?${params}`;
}

export function mapCounts(data: RiskMapData) {
  return data.leyenda.map((level) => ({
    ...level,
    count: data.features.filter(
      (f) =>
        (f.properties.estado === 'disponible' ? f.properties.nivel_riesgo : null) === level.nivel,
    ).length,
  }));
}
