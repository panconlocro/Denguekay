import { lazy, Suspense } from 'react';
import type { ComponentProps } from 'react';
import type { RiskMap } from './RiskMap';
import type { SeriesChart } from './SeriesChart';
import { Loading } from './ui';

const Map = lazy(() => import('./RiskMap').then((m) => ({ default: m.RiskMap })));
const Chart = lazy(() => import('./SeriesChart').then((m) => ({ default: m.SeriesChart })));

export function RiskMapView(props: ComponentProps<typeof RiskMap>) {
  return (
    <Suspense fallback={<Loading label="Cargando mapa" />}>
      <Map {...props} />
    </Suspense>
  );
}
export function SeriesChartView(props: ComponentProps<typeof SeriesChart>) {
  return (
    <Suspense fallback={<Loading label="Cargando gráfico" />}>
      <Chart {...props} />
    </Suspense>
  );
}
