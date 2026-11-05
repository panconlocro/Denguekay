import type { Prediction } from '../api/types';
import { emissionTiming } from '../lib/dashboard';
import { date, number, weekLabel } from '../lib/format';

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
      aria-label="Vigencia y anticipación de las predicciones"
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
        <small>Fecha de generación; distinta de la actualización de la API.</small>
      </div>
      <div>
        <strong>Anticipación efectiva mínima</strong>
        <p>
          {!timing
            ? 'No disponible'
            : timing.minimumWeeks <= 0
              ? 'Sin anticipación'
              : timing.minimumWeeks < 0.1
                ? 'Menos de 0,1 semanas'
                : `${number(Math.floor(timing.minimumWeeks * 10) / 10, 1)} semanas`}
        </p>
        <small>
          Entre los distritos con predicción disponible.{' '}
          {!timing
            ? 'Faltan fechas de emisión.'
            : timing.minimumWeeks <= 0
              ? 'La emisión ocurrió al inicio o después del inicio de la semana objetivo.'
              : timing.minimumWeeks < 2
                ? 'No alcanza el mínimo de 2 semanas desde la emisión.'
                : 'Alcanza 2 semanas desde la emisión; el estado de validación del modelo se indica aparte.'}
        </small>
      </div>
    </section>
  );
}
