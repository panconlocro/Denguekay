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

export const BOUNDARY_ATTRIBUTION =
  'Límites: Instituto Geográfico Nacional (IGN), publicados por OCHA en HDX (COD-AB de Perú), CC BY-IGO 3.0';

// What the map shows: district limits (Polygon or MultiPolygon), centroids (Point) or a mix when a limit is missing.
export function mapCopy(data: RiskMapData) {
  const points = data.features.filter((f) => f.geometry.type === 'Point').length;
  if (!data.features.length || points === data.features.length)
    return {
      note: 'Centroides distritales · no son límites territoriales',
      subtitle: 'Centroides distritales · selección con clic, Enter o barra espaciadora',
      footnote: 'Los puntos no delimitan el territorio; la leyenda procede de la API.',
    };
  const limits = 'Límites distritales simplificados para el mapa; no sirven para medir áreas.';
  return points
    ? {
        note: `Límites distritales · centroide donde falta el límite (${points}) · ${BOUNDARY_ATTRIBUTION}`,
        subtitle: 'Límites distritales · selección con clic, Enter o barra espaciadora',
        footnote: `${limits} ${points} distritos sin límite se muestran como punto. ${BOUNDARY_ATTRIBUTION}.`,
      }
    : {
        note: `Límites distritales · ${BOUNDARY_ATTRIBUTION}`,
        subtitle: 'Límites distritales · selección con clic, Enter o barra espaciadora',
        footnote: `${limits} ${BOUNDARY_ATTRIBUTION}. La leyenda procede de la API.`,
      };
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
