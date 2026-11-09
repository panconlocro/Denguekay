import type { Dashboard, District, Prediction } from '../api/types';

export function inSelection(
  ubigeo: string,
  districts: District[],
  province: string,
  district: string,
) {
  return (
    (!district || district === ubigeo) &&
    (!province || districts.some((d) => d.ubigeo === ubigeo && d.ubigeo_provincia === province))
  );
}

export function sortPredictions(rows: Prediction[]) {
  return [...rows].sort(
    (a, b) =>
      (b.probabilidad_brote ?? -1) - (a.probabilidad_brote ?? -1) ||
      a.ubigeo.localeCompare(b.ubigeo),
  );
}

export function consistentPredictions(rows: Prediction[], horizon: number) {
  const first = rows[0];
  return (
    !!first &&
    rows.every(
      (p) =>
        p.horizonte === horizon &&
        p.semana_corte.id_semana === first.semana_corte.id_semana &&
        p.semana_objetivo.id_semana === first.semana_objetivo.id_semana,
    )
  );
}

// A published aggregate can be marked available even when a district or its magnitude is missing.
export function regionalForecast(summary: Dashboard, rows?: Prediction[]) {
  const indicator = summary.casos_estimados_region;
  if (!summary.disponible || !indicator.disponible || indicator.valor == null)
    return {
      value: null,
      reason: indicator.motivo || summary.motivo || 'Sin magnitud regional publicada.',
    };
  if (!rows)
    return { value: null, reason: 'No se ha podido comprobar la cobertura de las predicciones.' };
  if (
    !consistentPredictions(rows, summary.horizonte) ||
    rows[0].semana_corte.id_semana !== summary.semana_corte?.id_semana ||
    rows[0].semana_objetivo.id_semana !== summary.semana_objetivo?.id_semana
  )
    return {
      value: null,
      reason: 'Resumen y predicciones no comparten el mismo corte y objetivo.',
    };
  const complete = rows.filter((p) => p.disponible && p.casos_estimados != null);
  if (
    summary.distritos <= 0 ||
    summary.distritos_con_prediccion !== summary.distritos ||
    rows.length !== summary.distritos ||
    new Set(complete.map((p) => p.ubigeo)).size !== summary.distritos
  )
    return {
      value: null,
      reason: `Cobertura incompleta: ${new Set(complete.map((p) => p.ubigeo)).size} de ${summary.distritos} distritos con magnitud. No se presenta un total regional.`,
    };
  return {
    value: indicator.valor,
    reason: `${summary.distritos} de ${summary.distritos} distritos con magnitud · casos estimados`,
  };
}

export function emissionTiming(rows: Prediction[]) {
  const available = rows.filter((p) => p.disponible);
  if (!available.length) return null;
  const timings = available.map((p) => ({
    generated: Date.parse(p.fecha_generacion),
    // Epidemiological weeks start at midnight in Piura (UTC-5), not UTC midnight.
    target: Date.parse(`${p.semana_objetivo.fecha_inicio}T00:00:00-05:00`),
  }));
  if (timings.some((p) => !Number.isFinite(p.generated) || !Number.isFinite(p.target))) return null;
  return {
    first: new Date(Math.min(...timings.map((p) => p.generated))).toISOString(),
    last: new Date(Math.max(...timings.map((p) => p.generated))).toISOString(),
    minimumWeeks: Math.min(...timings.map((p) => (p.target - p.generated) / (7 * 86400000))),
  };
}
