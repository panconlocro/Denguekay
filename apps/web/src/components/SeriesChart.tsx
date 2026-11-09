import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { get } from '../api/client';
import { useObservations } from '../api/queries';
import type { Series } from '../api/types';
import { date, number } from '../lib/format';
import {
  missingBands,
  seriesPoints,
  seriesRangeError,
  shiftWeeks,
  weekMilliseconds,
} from '../lib/series';
import { Empty, Failure, Loading } from './ui';

export function SeriesChart({ ubigeo, horizon }: { ubigeo: string; horizon: number }) {
  const [params, setParams] = useSearchParams();
  const mode =
    params.get('serie_ventana') === '52'
      ? '52'
      : params.get('serie_ventana') === 'custom'
        ? 'custom'
        : '26';
  const [openForm, setOpenForm] = useState(mode === 'custom');
  const [formError, setFormError] = useState<string | null>(null);
  const base = useQuery({
    queryKey: ['series', ubigeo, horizon],
    queryFn: ({ signal }) =>
      get('/api/v1/series/{ubigeo}', { horizonte: horizon }, signal, { ubigeo }),
  });
  const from =
    mode === 'custom'
      ? params.get('serie_desde') || ''
      : mode === '52' && base.data && !base.isError
        ? shiftWeeks(base.data.hasta, -51)
        : undefined;
  const to =
    mode === 'custom'
      ? params.get('serie_hasta') || ''
      : mode === '52'
        ? base.data?.hasta
        : undefined;
  const rangeError = mode === 'custom' ? seriesRangeError(from || '', to || '') : null;
  const ranged = useQuery({
    queryKey: ['series-range', ubigeo, horizon, from, to],
    enabled: !!from && !!to && !rangeError,
    queryFn: ({ signal }) =>
      get('/api/v1/series/{ubigeo}', { horizonte: horizon, desde: from, hasta: to }, signal, {
        ubigeo,
      }),
  });
  const query = mode === 'custom' || (mode === '52' && from) ? ranged : base;
  const setWindow = (window: string) => {
    const next = new URLSearchParams(params);
    next.set('serie_ventana', window);
    next.delete('serie_desde');
    next.delete('serie_hasta');
    setFormError(null);
    setOpenForm(false);
    setParams(next);
  };
  return (
    <>
      <div className="series-controls" role="group" aria-label="Rango de la serie">
        <button aria-pressed={mode === '26'} onClick={() => setWindow('26')}>
          Últimas 26 semanas
        </button>
        <button aria-pressed={mode === '52'} onClick={() => setWindow('52')}>
          52 semanas
        </button>
        <button aria-expanded={openForm} onClick={() => setOpenForm(!openForm)}>
          Rango personalizado
        </button>
      </div>
      {openForm && (
        <form
          className="series-range-form"
          key={`${ubigeo}/${horizon}/${query.data?.desde}/${query.data?.hasta}`}
          onSubmit={(event) => {
            event.preventDefault();
            const fields = new FormData(event.currentTarget);
            const start = String(fields.get('from'));
            const end = String(fields.get('to'));
            const error = seriesRangeError(start, end);
            setFormError(error);
            if (error) return;
            const next = new URLSearchParams(params);
            next.set('serie_ventana', 'custom');
            next.set('serie_desde', start);
            next.set('serie_hasta', end);
            setParams(next);
          }}
        >
          <label>
            Desde (domingo)
            <input
              type="date"
              name="from"
              aria-label="Inicio de la serie"
              defaultValue={from || query.data?.desde}
              required
            />
          </label>
          <label>
            Hasta (domingo)
            <input
              type="date"
              name="to"
              aria-label="Fin de la serie"
              defaultValue={to || query.data?.hasta}
              required
            />
          </label>
          <button className="button primary" type="submit">
            Aplicar rango
          </button>
          {formError && (
            <p className="range-error" role="alert">
              {formError}
            </p>
          )}
        </form>
      )}
      {rangeError ? (
        <Empty title="Rango de fechas no válido">
          {rangeError} Puedes volver a 26 o 52 semanas.
        </Empty>
      ) : query.isError ? (
        <Failure error={query.error} retry={() => void query.refetch()} />
      ) : !query.data ? (
        <Loading label="Cargando serie semanal" />
      ) : !query.data.disponible ? (
        <Empty>{query.data.motivo}</Empty>
      ) : (
        <SeriesContent series={query.data} />
      )}
    </>
  );
}

function SeriesContent({ series }: { series: Series }) {
  const observations = useObservations(series.ubigeo, series.desde, series.hasta);
  const points = seriesPoints(
    series,
    observations.isError || !observations.data?.disponible ? [] : observations.data.elementos,
  );
  if (!points.length || !points.some((p) => p.observed != null || p.predicted != null))
    return <Empty title="Sin valores para este intervalo">{series.motivo}</Empty>;
  const bands = missingBands(points);
  const afterCut = points.find((p) => p.afterCut);
  const halfWeek = weekMilliseconds / 2;
  const labels = new Map(points.map((p) => [p.x, p.label]));
  return (
    <>
      {observations.isPending && (
        <p className="scope-note" role="status">
          Consultando umbral observado por semana…
        </p>
      )}
      {observations.isError && (
        <div className="threshold-error">
          <h3>Umbral observado no disponible</h3>
          <Failure error={observations.error} retry={() => void observations.refetch()} />
        </div>
      )}
      <div
        className="chart"
        role="img"
        aria-label={`Serie de casos observados y pronosticados de ${series.distrito}. Umbral histórico por semana; líneas interrumpidas donde faltan datos.`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 18, right: 18, left: -10, bottom: 5 }}>
            <CartesianGrid vertical={false} stroke="#ece9e2" />
            <XAxis
              type="number"
              dataKey="x"
              domain={[points[0].x - halfWeek, points[points.length - 1].x + halfWeek]}
              ticks={points
                .filter((_, i) => i % Math.max(1, Math.ceil(points.length / 6)) === 0)
                .map((p) => p.x)}
              tickFormatter={(value) => labels.get(value) || ''}
              tick={{ fontSize: 10, fill: 'var(--muted)' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: 'var(--muted)' }}
              axisLine={false}
              tickLine={false}
              width={55}
            />
            <Tooltip
              labelFormatter={(value) =>
                labels.get(Number(value)) || date(new Date(Number(value)).toISOString())
              }
              formatter={(value, name) => [number(value == null ? null : Number(value), 2), name]}
              contentStyle={{ borderRadius: 10, borderColor: '#e3dfd7', fontSize: 12 }}
            />
            {afterCut && (
              <ReferenceArea
                x1={afterCut.x - halfWeek}
                x2={points[points.length - 1].x + halfWeek}
                fill="#0b5d63"
                fillOpacity={0.06}
              />
            )}
            {bands.map((band) => (
              <ReferenceArea
                key={band.from}
                x1={band.from}
                x2={band.to}
                fill="#a5abb2"
                fillOpacity={0.2}
              />
            ))}
            <Line
              type="linear"
              dataKey="observed"
              name="Observado (casos)"
              stroke="#17202a"
              strokeWidth={2}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
            <Line
              type="linear"
              dataKey="predicted"
              name="Pronosticado (casos)"
              stroke="#0b5d63"
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={{ r: 2 }}
              connectNulls={false}
              isAnimationActive={false}
            />
            <Line
              type="linear"
              dataKey="threshold"
              name="Umbral observado (casos)"
              stroke="#b3312e"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-legend">
        <span>
          <i />
          Observado
        </span>
        <span>
          <i className="dashed" />
          Pronosticado · h = {series.horizonte}
        </span>
        <span>
          <i className="threshold-line" />
          Umbral observado
        </span>
        <span>Gris: semana histórica sin observación</span>
        <span>Fondo verde azulado: posterior al corte</span>
      </div>
      <p className="footnote">
        {series.distrito} · {date(series.desde)} – {date(series.hasta)} · {points.length} semanas.
        Las predicciones históricas son retrospectivas; no son casos confirmados. Las líneas se
        interrumpen donde faltan datos y el umbral histórico no se extrapola a semanas sin
        observación. Solo se representan las semanas publicadas dentro del intervalo.
      </p>
      <details className="data-details">
        <summary>Ver datos de la serie en tabla</summary>
        <div
          className="table-scroll"
          tabIndex={0}
          role="region"
          aria-label="Datos de la serie semanal"
        >
          <table className="series-data">
            <thead>
              <tr>
                <th>Semana</th>
                <th>Observado</th>
                <th>Pronosticado</th>
                <th>Umbral observado</th>
                <th>Intervalo</th>
                <th>Origen del pronóstico</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.x}>
                  <th scope="row">{p.label}</th>
                  <td>{number(p.observed)}</td>
                  <td>{number(p.predicted, 2)}</td>
                  <td>{number(p.threshold, 2)}</td>
                  <td>{p.interval || 'No disponible'}</td>
                  <td>{p.origin}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}
