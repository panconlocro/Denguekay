import { useNavigate } from 'react-router-dom';
import { useOutletContext } from 'react-router-dom';
import type { AppContext } from '../App';
import { useAlerts, usePredictions, useRiskMap, useSummary } from '../api/queries';
import type { Dashboard } from '../api/types';
import { date, horizonStatus, number, percent, targetPassed, weekLabel } from '../lib/format';
import { AppLink, Card, DataTag, Empty, Failure, Loading, RiskChip } from '../components/ui';

import { RiskMapView as RiskMap, SeriesChartView as SeriesChart } from '../components/Visuals';

export function DashboardPage() {
  const context = useOutletContext<AppContext>();
  const { configuration, horizon, enabled, districts, province, district, search } = context;
  const summary = useSummary(horizon, enabled);
  const predictions = usePredictions(horizon, enabled);
  const map = useRiskMap(horizon, enabled);
  const alerts = useAlerts(horizon, enabled);
  const navigate = useNavigate();
  const selected = (ubigeo: string) =>
    (!district || district === ubigeo) &&
    (!province || districts.find((d) => d.ubigeo === ubigeo)?.ubigeo_provincia === province);
  const rows = (predictions.data?.elementos || [])
    .filter((p) => p.disponible && selected(p.ubigeo))
    .sort((a, b) => (b.probabilidad_brote ?? -1) - (a.probabilidad_brote ?? -1));
  const alertRows = (alerts.data?.elementos || []).filter((a) => selected(a.ubigeo));
  const visibleMap = map.data
    ? { ...map.data, features: map.data.features.filter((f) => selected(f.id)) }
    : undefined;
  const experimental = configuration.horizontes.find((h) => h.horizonte === horizon)?.experimental;

  if (!enabled)
    return (
      <Card>
        <Empty title="Horizonte no disponible">
          {configuration.horizontes.find((h) => h.horizonte === horizon)?.motivo ||
            'No hay un modelo disponible para este horizonte.'}
        </Empty>
      </Card>
    );
  return (
    <>
      {(province || district) && (
        <div className="scope-note">
          Los filtros geográficos se aplican al mapa, al listado y a los avisos. Los cuatro
          indicadores superiores mantienen el alcance <strong>regional</strong>.
        </div>
      )}
      {summary.isError ? (
        <Card>
          <Failure error={summary.error} retry={() => void summary.refetch()} />
        </Card>
      ) : summary.isPending ? (
        <Card>
          <Loading label="Cargando indicadores regionales" />
        </Card>
      ) : (
        <Indicators summary={summary.data} />
      )}
      <div className="dashboard-top">
        <Card
          title={`Mapa de riesgo · ${weekLabel(summary.data?.semana_objetivo)}`}
          subtitle={`Probabilidad de brote por distrito · h = ${horizon} semanas`}
          action={
            <AppLink to="/mapa" className="text-link">
              Abrir mapa →
            </AppLink>
          }
        >
          {map.isError ? (
            <Failure error={map.error} retry={() => void map.refetch()} />
          ) : !visibleMap ? (
            <Loading label="Cargando mapa distrital" />
          ) : !visibleMap.features.length ? (
            <Empty title="Sin distritos para esta selección" />
          ) : (
            <RiskMap data={visibleMap} select={(id) => navigate(`/distritos/${id}${search}`)} />
          )}
        </Card>
        <Card
          title="Distritos prioritarios"
          subtitle="Ordenados por probabilidad de brote · corte publicado"
          action={
            <AppLink to="/alertas" className="text-link">
              Ver avisos →
            </AppLink>
          }
        >
          {predictions.isError ? (
            <Failure error={predictions.error} retry={() => void predictions.refetch()} />
          ) : predictions.isPending ? (
            <Loading label="Cargando predicciones" />
          ) : !rows.length ? (
            <Empty title="Sin predicciones disponibles">{predictions.data.motivo}</Empty>
          ) : (
            <>
              <div className="table-scroll">
                <table className="priorities">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Distrito</th>
                      <th>Probabilidad de brote</th>
                      <th>Nivel</th>
                      <th>Casos est.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.slice(0, 9).map((p, i) => (
                      <tr key={p.ubigeo}>
                        <td>{i + 1}</td>
                        <td>
                          <AppLink to={`/distritos/${p.ubigeo}`}>
                            <strong>{p.distrito}</strong>
                          </AppLink>
                          <small>
                            Prov.{' '}
                            {districts.find((d) => d.ubigeo === p.ubigeo)?.provincia || 'Sin dato'}
                          </small>
                        </td>
                        <td>
                          <div className="probability">
                            <span className={`probability-track risk-${p.nivel_riesgo}`}>
                              <i style={{ width: `${(p.probabilidad_brote ?? 0) * 100}%` }} />
                            </span>
                            <strong>{percent(p.probabilidad_brote)}</strong>
                          </div>
                        </td>
                        <td>
                          <RiskChip level={p.nivel_riesgo} label={p.nivel_riesgo_etiqueta} />
                        </td>
                        <td>
                          {p.casos_estimados == null
                            ? 'Sin datos'
                            : `≈ ${number(p.casos_estimados)}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="footnote">
                Se muestran {Math.min(9, rows.length)} de {rows.length} distritos con predicción
                disponible. Los casos son estimaciones para la semana objetivo.
              </p>
            </>
          )}
        </Card>
      </div>
      <div className="dashboard-bottom">
        <Card
          title={
            district
              ? `Serie temporal · ${districts.find((d) => d.ubigeo === district)?.nombre || district}`
              : 'Serie regional: casos observados y pronosticados'
          }
          subtitle={
            district
              ? 'Casos por semana epidemiológica · observado frente a pronosticado'
              : 'Disponibilidad de la serie histórica regional'
          }
        >
          {district ? (
            <SeriesChart ubigeo={district} horizon={horizon} />
          ) : (
            <div className="regional-unavailable">
              <div className="chart-placeholder" aria-hidden="true">
                <div />
                <div />
                <div />
                <div />
              </div>
              <Empty title="Serie regional no disponible">
                La API actual publica series por distrito. Selecciona un distrito en los filtros o
                en el mapa para explorar su serie; no se estima una curva regional con datos
                incompletos.
              </Empty>
            </div>
          )}
        </Card>
        <div className="stack">
          <Card
            title={experimental ? 'Avisos experimentales' : 'Alertas tempranas activas'}
            subtitle={`${weekLabel(summary.data?.semana_objetivo)} · h = ${horizon} semanas`}
          >
            {alerts.isError ? (
              <Failure error={alerts.error} retry={() => void alerts.refetch()} />
            ) : alerts.isPending ? (
              <Loading label="Cargando avisos" />
            ) : !alertRows.length ? (
              <Empty title={experimental ? 'Sin avisos experimentales' : 'Sin alertas activas'}>
                No hay registros para los filtros seleccionados.
              </Empty>
            ) : (
              <div className="alert-preview">
                {alertRows.slice(0, 3).map((a) => (
                  <AppLink
                    key={a.id_alerta}
                    to={`/distritos/${a.ubigeo}`}
                    className={`alert-row risk-${a.nivel}`}
                  >
                    <div>
                      <strong>{a.distrito}</strong>
                      <small>
                        Prob. {percent(a.prediccion.probabilidad_brote)} ·{' '}
                        {weekLabel(a.prediccion.semana_objetivo)}
                      </small>
                    </div>
                    <RiskChip level={a.nivel} label={a.nivel_etiqueta} />
                  </AppLink>
                ))}
              </div>
            )}
            <AppLink to="/alertas" className="button primary full-width">
              Ver {experimental ? 'avisos' : 'alertas'} (
              {alerts.isError ? '—' : number(alertRows.length)}) →
            </AppLink>
          </Card>
          <Card
            title="Estado de los horizontes"
            action={
              <AppLink to="/modelo" className="text-link">
                Ver desempeño →
              </AppLink>
            }
          >
            <div className="horizon-list">
              {configuration.horizontes.map((h) => (
                <div key={h.horizonte}>
                  <span>
                    {h.horizonte} semanas{h.horizonte === 4 ? ' (meta)' : ''}
                  </span>
                  <strong
                    className={
                      h.experimental
                        ? 'experimental-text'
                        : h.disponible
                          ? 'operational-text'
                          : 'muted'
                    }
                  >
                    ● {horizonStatus(h)}
                  </strong>
                </div>
              ))}
            </div>
            <p className="footnote">
              Disponible no significa validado. Los avisos experimentales no son alertas operativas
              ni generan notificaciones.
            </p>
          </Card>
        </div>
      </div>
    </>
  );
}

function Indicators({ summary }: { summary: Dashboard }) {
  return (
    <div className="indicators" aria-label="Indicadores de la región Piura">
      <Card>
        <DataTag observed />
        <p className="metric-label">Casos observados · última semana</p>
        <strong className="metric-value">
          {summary.casos_observados_ultima_semana.disponible
            ? number(summary.casos_observados_ultima_semana.valor)
            : 'No disponible'}
        </strong>
        <p className="metric-note">
          {summary.casos_observados_ultima_semana.motivo ||
            'Región Piura · según el resumen de la API. Cobertura distrital no informada.'}
        </p>
      </Card>
      <Card>
        <DataTag />
        <p className="metric-label">Distritos en nivel Alto o Muy alto</p>
        <strong className="metric-value warm">
          {summary.disponible
            ? `${number((summary.niveles_riesgo.alto || 0) + (summary.niveles_riesgo.muy_alto || 0))} de ${number(summary.distritos)}`
            : 'No disponible'}
        </strong>
        <p className="metric-note">
          {summary.experimental ? 'Avisos experimentales' : 'Corte publicado'} ·{' '}
          {weekLabel(summary.semana_objetivo)}
        </p>
      </Card>
      <Card>
        <DataTag />
        <p className="metric-label">Magnitud regional estimada</p>
        <strong className="metric-value">
          {summary.casos_estimados_region.disponible
            ? `≈ ${number(summary.casos_estimados_region.valor)}`
            : 'No disponible'}
        </strong>
        <p className="metric-note">
          {summary.casos_estimados_region.motivo ||
            `${number(summary.distritos_con_prediccion)} distritos con predicción · casos estimados`}
        </p>
      </Card>
      <Card className="unavailable-card">
        <DataTag observed />
        <p className="metric-label">Incidencia por 100 000 habitantes</p>
        <strong className="metric-value muted">No disponible</strong>
        <p className="metric-note">
          La API no publica incidencia ni la población del periodo necesaria para calcularla.
        </p>
      </Card>
      <div className="indicators-note">
        Corte de observación: {weekLabel(summary.semana_corte)} · objetivo:{' '}
        {weekLabel(summary.semana_objetivo)} · actualización: {date(summary.fecha_actualizacion)}
        {targetPassed(summary.semana_objetivo)
          ? ' · Semana objetivo pasada; consulta histórica.'
          : ''}
      </div>
    </div>
  );
}
