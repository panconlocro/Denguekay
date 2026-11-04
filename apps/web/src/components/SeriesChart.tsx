import { useQuery } from '@tanstack/react-query';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { get } from '../api/client';
import { date, number, weekLabel } from '../lib/format';
import { Empty, Failure, Loading } from './ui';

export function SeriesChart({ ubigeo, horizon }: { ubigeo: string; horizon: number }) {
  const query = useQuery({
    queryKey: ['series', ubigeo, horizon],
    queryFn: ({ signal }) =>
      get('/api/v1/series/{ubigeo}', { horizonte: horizon }, signal, { ubigeo }),
  });
  if (query.isError) return <Failure error={query.error} retry={() => void query.refetch()} />;
  if (!query.data) return <Loading label="Cargando serie semanal" />;
  const series = query.data;
  const points = series.elementos.map((s) => ({
    label: weekLabel(s.semana),
    start: date(s.semana.fecha_inicio),
    observed: s.casos_dengue,
    predicted: s.prediccion?.disponible ? s.prediccion.casos_estimados : null,
  }));
  if (!points.some((p) => p.observed != null || p.predicted != null))
    return <Empty>{series.motivo}</Empty>;
  return (
    <>
      <div
        className="chart"
        role="img"
        aria-label={`Serie de casos observados y pronosticados de ${series.distrito}. Las líneas se interrumpen donde faltan datos.`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 18, right: 12, left: -15, bottom: 5 }}>
            <CartesianGrid vertical={false} stroke="#ece9e2" />
            <XAxis
              dataKey="label"
              minTickGap={42}
              tick={{ fontSize: 10, fill: '#8a929c' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: '#8a929c' }}
              axisLine={false}
              tickLine={false}
              width={55}
            />
            <Tooltip
              formatter={(value, name) => [number(value == null ? null : Number(value), 2), name]}
              contentStyle={{ borderRadius: 10, borderColor: '#e3dfd7', fontSize: 12 }}
            />
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
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-legend">
        <span>
          <i /> Observado
        </span>
        <span>
          <i className="dashed" /> Pronosticado · h = {horizon}
        </span>
        <span>Sin datos: la línea se interrumpe</span>
      </div>
      <p className="footnote">
        {series.distrito} · {date(series.desde)} – {date(series.hasta)} · casos por semana
        epidemiológica. Las predicciones históricas son retrospectivas.
      </p>
      <details className="data-details">
        <summary>Ver datos de la serie en tabla</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Semana</th>
                <th>Observado</th>
                <th>Pronosticado</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.label}>
                  <td>{p.label}</td>
                  <td>{number(p.observed)}</td>
                  <td>{number(p.predicted, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}
