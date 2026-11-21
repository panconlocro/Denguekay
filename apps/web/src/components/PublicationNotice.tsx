import type { Prediction } from '../api/types';
import { emissionTiming } from '../lib/dashboard';
import { date, weekLabel } from '../lib/format';

export function PublicationNotice({
  rows,
  scopeLabel = 'Región Piura',
}: {
  rows: Prediction[];
  scopeLabel?: string;
}) {
  const timing = emissionTiming(rows);
  const first = rows[0];
  if (!first) return null;
  return (
    <section
      className="publication-notice"
      aria-label="Corte, objetivo y emisión de las predicciones"
    >
      <div>
        <strong>Corte y objetivo · {scopeLabel}</strong>
        <p>
          {weekLabel(first.semana_corte)} → {weekLabel(first.semana_objetivo)}
        </p>
        <small>
          Objetivo: {date(first.semana_objetivo.fecha_inicio)} –{' '}
          {date(first.semana_objetivo.fecha_fin)}
        </small>
      </div>
      <div>
        <strong>Emisión del pronóstico</strong>
        <p>
          {timing
            ? date(timing.first) === date(timing.last)
              ? date(timing.last)
              : `${date(timing.first)} – ${date(timing.last)}`
            : 'No disponible'}
        </p>
        <small>
          Fecha de generación; distinta de la actualización de la API. El horizonte se cuenta desde
          la semana de corte.
        </small>
      </div>
    </section>
  );
}
