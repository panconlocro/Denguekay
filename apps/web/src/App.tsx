import { useQuery } from '@tanstack/react-query';
import { Suspense } from 'react';
import {
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
  useMatch,
  useNavigate,
  useSearchParams,
} from 'react-router-dom';
import { get } from './api/client';
import { useDistricts, useSummary } from './api/queries';
import type { Configuration, District } from './api/types';
import { Filters } from './components/Filters';
import { SourceNotice } from './components/SourceNotice';
import { Card, Failure, Icon, Loading } from './components/ui';
import { dataSource, verifyDemoV2 } from './lib/dataSource';
import { date, targetStarted, weekLabel } from './lib/format';
import { DashboardPage } from './pages/DashboardPage';
import { MapPage } from './pages/MapPage';
import { DistrictPage } from './pages/DistrictPage';
import { AlertsPage, AlertDetailPage } from './pages/AlertsPage';
import { NotFoundPage } from './pages/SecondaryPages';
import { ModelsPage } from './pages/ModelsPage';
import { HelpPage } from './pages/HelpPage';

export type AppContext = {
  configuration: Configuration;
  districts: District[];
  horizon: number;
  enabled: boolean;
  province: string;
  district: string;
  search: string;
  catalogueReady: boolean;
  cataloguePending: boolean;
};

const navigation = [
  { to: '/', name: 'Tablero', short: 'Tablero', icon: 'grid' },
  { to: '/mapa', name: 'Mapa de riesgo', short: 'Mapa', icon: 'map' },
  { to: '/distritos', name: 'Detalle y series', short: 'Series', icon: 'series' },
  { to: '/alertas', name: 'Alertas tempranas', short: 'Avisos', icon: 'alert' },
  { to: '/modelo', name: 'Desempeño del modelo', short: 'Modelo', icon: 'bars' },
  { to: '/ayuda', name: 'Ayuda y manual', short: 'Ayuda', icon: 'help' },
];

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="mapa" element={<MapPage />} />
        <Route path="distritos" element={<DistrictPage />} />
        <Route path="distritos/:ubigeo" element={<DistrictPage />} />
        <Route path="alertas" element={<AlertsPage />} />
        <Route path="alertas/:id" element={<AlertDetailPage />} />
        <Route path="modelo" element={<ModelsPage />} />
        <Route path="ayuda" element={<HelpPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const match = useMatch('/distritos/:ubigeo');
  const alertMatch = useMatch('/alertas/:id');
  const source = dataSource(import.meta.env.VITE_DATA_SOURCE);
  const identity = useQuery({
    queryKey: ['demo-v2-identity'],
    enabled: source === 'demo-v2',
    queryFn: async ({ signal }) => {
      const models = await get('/api/v1/modelos/activo', {}, signal);
      verifyDemoV2(models.elementos);
      return models;
    },
  });
  const sourceReady = source !== 'demo-v2' || (identity.isSuccess && !identity.isError);
  const config = useQuery({
    queryKey: ['configuration'],
    queryFn: ({ signal }) => get('/api/v1/configuracion', {}, signal),
  });
  const catalogue = useDistricts();
  const [params, setParams] = useSearchParams();
  const configuration = config.isError || !sourceReady ? undefined : config.data;
  const requestedHorizon = Number(params.get('horizonte'));
  const horizon = configuration?.horizontes.some((h) => h.horizonte === requestedHorizon)
    ? requestedHorizon
    : (configuration?.horizonte_por_defecto ?? 4);
  const enabled = !!configuration?.horizontes.find((h) => h.horizonte === horizon)?.disponible;
  const summary = useSummary(horizon, enabled);
  const districts = catalogue.isError ? [] : catalogue.data?.elementos || [];
  const district = match?.params.ubigeo || params.get('distrito') || '';
  const province = match
    ? districts.find((d) => d.ubigeo === district)?.ubigeo_provincia || ''
    : params.get('provincia') || '';
  const navigationParams = new URLSearchParams(params);
  if (match) {
    navigationParams.set('distrito', district);
    if (province) navigationParams.set('provincia', province);
  }
  const search = navigationParams.toString() ? `?${navigationParams}` : '';
  const change = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.delete('aviso_pagina');
    if (value) next.set(key, value);
    else next.delete(key);
    if (key === 'provincia') next.delete('distrito');
    if (alertMatch) navigate(`/alertas?${next}`);
    else if (match && (key === 'distrito' || key === 'provincia'))
      navigate(`/distritos${key === 'distrito' && value ? `/${value}` : ''}?${next}`);
    else setParams(next);
  };
  const reset = () => {
    if (alertMatch) navigate('/alertas');
    else if (match) navigate('/distritos');
    else setParams({});
  };
  const title =
    location.pathname === '/'
      ? 'Tablero de vigilancia y pronóstico'
      : navigation.find((n) => n.to !== '/' && location.pathname.startsWith(n.to))?.name ||
        'Página no encontrada';
  const currentSummary = !configuration || summary.isError ? undefined : summary.data;
  const context = configuration
    ? {
        configuration,
        districts,
        horizon,
        enabled,
        province,
        district,
        search,
        catalogueReady: catalogue.isSuccess && !catalogue.isError && !!catalogue.data?.disponible,
        cataloguePending: catalogue.isPending,
      }
    : null;
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Saltar al contenido
      </a>
      <aside className="sidebar">
        <NavLink className="brand" to={`/${search}`} aria-label="Denguekay, inicio">
          <img src="/assets/logo.svg" width="34" height="34" alt="" />
          <span>
            <strong>Denguekay</strong>
            <small>Alerta temprana de dengue · Piura</small>
          </span>
        </NavLink>
        <p className="nav-caption">MENÚ</p>
        <nav aria-label="Navegación principal">
          {navigation.map((item) => (
            <NavLink key={item.to} to={`${item.to}${search}`} end={item.to === '/'}>
              <Icon name={item.icon} />
              <span>{item.name}</span>
              {item.to === '/alertas' && currentSummary && (
                <span className="nav-count">{currentSummary.alertas_activas}</span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="institution">
          <strong>DIRESA Piura</strong>
          <span>Epidemiología y vigilancia</span>
          <small>
            Datos públicos agregados por distrito.
            <br />
            Sin datos personales (Ley N.º 29733).
          </small>
        </div>
      </aside>
      <main id="main-content" className="main-content" tabIndex={-1}>
        <header className="page-header">
          <div>
            <p className="eyebrow">DENGUEKAY / VIGILANCIA DISTRITAL</p>
            <h1>{title}</h1>
            <p>
              Situación observada y pronóstico de brotes de dengue por distrito y semana — Región
              Piura
            </p>
          </div>
          <div className="freshness">
            <span className="date-pill">
              <i />
              {configuration
                ? `Actualizado ${date(currentSummary?.fecha_actualizacion || configuration.fecha_actualizacion)}`
                : 'Conectando con la API'}
            </span>
            <span>Objetivo: {weekLabel(currentSummary?.semana_objetivo)}</span>
            {targetStarted(currentSummary?.semana_objetivo) && (
              <strong className="historical-pill">Consulta histórica · objetivo iniciado</strong>
            )}
          </div>
        </header>
        <SourceNotice
          source={source}
          verified={sourceReady}
          cutoff={identity.data?.fecha_corte_datos}
        />
        {source === 'demo-v2' && identity.isError ? (
          <Card>
            <Failure error={identity.error} retry={() => void identity.refetch()} />
          </Card>
        ) : config.isError ? (
          <Card>
            <Failure error={config.error} retry={() => void config.refetch()} />
          </Card>
        ) : !configuration ? (
          <Card>
            <Loading label="Conectando con el servicio de predicción" />
          </Card>
        ) : (
          <>
            <Filters
              configuration={configuration}
              districts={districts}
              horizon={horizon}
              province={province}
              district={district}
              target={currentSummary?.semana_objetivo}
              change={change}
              reset={reset}
            />
            {configuration.horizontes.find((h) => h.horizonte === horizon)?.experimental && (
              <div className="experimental-banner" role="note">
                <span className="banner-symbol">!</span>
                <div>
                  <strong>Experimental: modelo no validado</strong>
                  <p>
                    Los pronósticos y avisos son experimentales; no constituyen alertas operativas.
                  </p>
                </div>
                <NavLink to={`/modelo${search}`}>Ver desempeño →</NavLink>
              </div>
            )}
            {catalogue.isError && (
              <Card>
                <Failure error={catalogue.error} retry={() => void catalogue.refetch()} />
              </Card>
            )}
            <Suspense
              fallback={
                <Card>
                  <Loading label="Cargando vista" />
                </Card>
              }
            >
              <Outlet context={context} />
            </Suspense>
          </>
        )}
        <footer className="page-footer">
          <span>Denguekay · Vigilancia de dengue en Piura</span>
          <span>Datos agregados · Contrato API {configuration?.version_contrato || '—'}</span>
        </footer>
      </main>
      <nav className="mobile-nav" aria-label="Navegación móvil">
        {navigation.map((item) => (
          <NavLink key={item.to} to={`${item.to}${search}`} end={item.to === '/'}>
            <Icon name={item.icon} />
            <span>{item.short}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
