import { useNavigate, useOutletContext } from 'react-router-dom';
import type { AppContext } from '../App';
import { useAlerts, usePredictions, useRiskMap, useSummary } from '../api/queries';
import type { Dashboard, Prediction } from '../api/types';
import {
  consistentPredictions,
  inSelection,
  regionalForecast,
  sortPredictions,
} from '../lib/dashboard';
import { date, horizonStatus, number, percent, targetStarted, weekLabel } from '../lib/format';
import { PriorityTable } from '../components/PriorityTable';
import { PublicationNotice } from '../components/PublicationNotice';
import { AppLink, Card, DataTag, Empty, Failure, Loading, RiskChip } from '../components/ui';
import { RiskMapView as RiskMap, SeriesChartView as SeriesChart } from '../components/Visuals';
import { alertProbability } from '../lib/alerts';

export function DashboardPage() {
  const {
    configuration,
    horizon,
    enabled,
    districts,
    province,
    district,
    search,
    catalogueReady,
    cataloguePending,
  } = useOutletContext<AppContext>();
  const summary = useSummary(horizon, enabled);
  const predictions = usePredictions(horizon, enabled);
  const map = useRiskMap(horizon, enabled);
  const alerts = useAlerts(horizon, enabled);
  const navigate = useNavigate();
  const selected = (ubigeo: string) => inSelection(ubigeo, districts, province, district);
  const scope = districts.filter((d) => d.activo && selected(d.ubigeo));
  const invalidSelection =
    catalogueReady &&
    ((!!province && !districts.some((d) => d.ubigeo_provincia === province)) ||
      (!!district && !scope.some((d) => d.ubigeo === district)));
  const currentPredictions = predictions.isError ? undefined : predictions.data;
  const coherent =
    !!currentPredictions?.disponible &&
    consistentPredictions(currentPredictions.elementos, horizon);
  const rows = coherent
    ? sortPredictions(
        currentPredictions.elementos.filter((p) => p.disponible && selected(p.ubigeo)),
      )
    : [];
  const mapData = map.isError ? undefined : map.data;
  const visibleMap = mapData
    ? { ...mapData, features: mapData.features.filter((f) => selected(f.id)) }
    : undefined;
  const currentAlerts = alerts.isError ? undefined : alerts.data;
  const alertRows = (currentAlerts?.disponible ? currentAlerts.elementos : [])
    .filter((a) => selected(a.ubigeo))
    .sort(
      (a, b) =>
        (alertProbability(b) ?? -1) - (alertProbability(a) ?? -1) ||
        a.ubigeo.localeCompare(b.ubigeo),
    );
  const experimental = configuration.horizontes.find((h) => h.horizonte === horizon)?.experimental;
  const geographicState = cataloguePending ? (
    <Loading label="Cargando catálogo geográfico" />
  ) : !catalogueReady ? (
    <Empty title="Catálogo geográfico no disponible">
      Reintenta la consulta del catálogo para aplicar los filtros.
    </Empty>
  ) : invalidSelection ? (
    <Empty title="Selección geográfica no válida">
      Revisa provincia y distrito o utiliza «Limpiar filtros».
    </Empty>
  ) : null;

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
      <div className="scope-note" role="note" aria-label="Alcance de los filtros">
        Indicadores: <strong>Región Piura</strong>. Mapa, listado y avisos:{' '}
        <strong>
          {invalidSelection
            ? 'Selección por revisar'
            : districts.find((d) => d.ubigeo === district)?.nombre ||
              districts.find((d) => d.ubigeo_provincia === province)?.provincia ||
              (province || district ? 'selección por revisar' : 'Región Piura')}
        </strong>
        .
        {(province || district) &&
          ' Los filtros geográficos no modifican los cuatro indicadores regionales.'}
      </div>
      {summary.isError ? (
        <Card>
          <Failure error={summary.error} retry={() => void summary.refetch()} />
        </Card>
      ) : summary.isPending ? (
        <Card>
          <Loading label="Cargando indicadores regionales" />
        </Card>
      ) : (
        <Indicators
          summary={summary.data}
          predictions={currentPredictions?.disponible ? currentPredictions.elementos : undefined}
        />
      )}
      {coherent && <PublicationNotice rows={currentPredictions.elementos} />}
      <div className="dashboard-top">
        <Card
          title={`Mapa de riesgo · ${weekLabel(mapData?.semana_objetivo)}`}
          subtitle={`Probabilidad de brote por distrito · h = ${horizon} semanas`}
          action={
            <AppLink to="/mapa" className="text-link">
              Abrir mapa →
            </AppLink>
          }
        >
          {geographicState ||
            (map.isError ? (
              <Failure error={map.error} retry={() => void map.refetch()} />
            ) : !visibleMap ? (
              <Loading label="Cargando mapa distrital" />
            ) : !visibleMap.features.length ? (
              <Empty title="Sin distritos para esta selección">{visibleMap.motivo}</Empty>
            ) : (
              <>
                <RiskMap data={visibleMap} select={(id) => navigate(`/distritos/${id}${search}`)} />
                <p className="footnote">
                  {visibleMap.features.length} de {scope.length} distritos representados ·{' '}
                  {
                    visibleMap.features.filter(
                      (f) =>
                        f.properties.estado !== 'disponible' || f.properties.nivel_riesgo == null,
                    ).length
                  }{' '}
                  sin nivel de riesgo. Corte: {weekLabel(visibleMap.semana_corte)}.{' '}
                  {visibleMap.motivo}
                </p>
              </>
            ))}
        </Card>
        <Card
          title="Distritos prioritarios"
          subtitle="Probabilidad descendente · empates por UBIGEO"
          action={
            <AppLink to="/distritos" className="text-link">
              Ver catálogo →
            </AppLink>
          }
        >
          {geographicState ||
            (predictions.isError ? (
              <Failure error={predictions.error} retry={() => void predictions.refetch()} />
            ) : predictions.isPending ? (
              <Loading label="Cargando predicciones" />
            ) : !coherent ? (
              <Empty title="Predicciones no disponibles">
                {currentPredictions?.motivo ||
                  'No hay una publicación con corte y objetivo coherentes para este horizonte.'}
              </Empty>
            ) : (
              <>
                <p className="scope-note">
                  {rows.length} de {scope.length} distritos de la selección con predicción
                  disponible · {weekLabel(currentPredictions.elementos[0].semana_objetivo)}.
                </p>
                {!rows.length ? (
                  <Empty title="Sin predicciones disponibles">
                    {currentPredictions.motivo ||
                      'Los distritos seleccionados no tienen predicción disponible en este corte.'}
                  </Empty>
                ) : (
                  <PriorityTable
                    key={`${horizon}/${province}/${district}/${currentPredictions.elementos[0].semana_corte.id_semana}`}
                    rows={rows}
                    districts={districts}
                  />
                )}
              </>
            ))}
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
            geographicState || <SeriesChart ubigeo={district} horizon={horizon} />
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
            subtitle={`Selección geográfica · h = ${horizon} semanas`}
          >
            {geographicState ||
              (alerts.isError ? (
                <Failure error={alerts.error} retry={() => void alerts.refetch()} />
              ) : alerts.isPending ? (
                <Loading label="Cargando avisos" />
              ) : !currentAlerts?.disponible ? (
                <Empty title="Avisos no disponibles">{currentAlerts?.motivo}</Empty>
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
                          Prob. {percent(alertProbability(a))} ·{' '}
                          {weekLabel(a.prediccion.semana_objetivo)}
                        </small>
                      </div>
                      <RiskChip level={a.nivel} label={a.nivel_etiqueta} />
                    </AppLink>
                  ))}
                </div>
              ))}
            <AppLink to="/alertas" className="button primary full-width">
              Ver {experimental ? 'avisos' : 'alertas'} (
              {!geographicState && currentAlerts?.disponible ? number(alertRows.length) : '—'}) →
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
              La validación del modelo y la vigencia del pronóstico son distintas. Para anticipar
              una intervención se requieren al menos 2 semanas efectivas desde la emisión. Los
              avisos experimentales no son alertas operativas ni generan notificaciones.
            </p>
          </Card>
        </div>
      </div>
    </>
  );
}

function Indicators({ summary, predictions }: { summary: Dashboard; predictions?: Prediction[] }) {
  const magnitude = regionalForecast(summary, predictions);
  const highRisk = summary.niveles_riesgo.alto;
  const veryHighRisk = summary.niveles_riesgo.muy_alto;
  return (
    <div className="indicators" role="group" aria-label="Indicadores de la región Piura">
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
          {summary.disponible && highRisk != null && veryHighRisk != null
            ? `${number(highRisk + veryHighRisk)} de ${number(summary.distritos)}`
            : 'No disponible'}
        </strong>
        <p className="metric-note">
          {summary.disponible
            ? `Evaluados: ${number(summary.distritos_con_prediccion)} de ${number(summary.distritos)} distritos con predicción.`
            : summary.motivo || 'Sin predicciones publicadas.'}{' '}
          {summary.experimental ? 'Avisos experimentales' : 'Corte publicado'} ·{' '}
          {weekLabel(summary.semana_objetivo)}
        </p>
      </Card>
      <Card>
        <DataTag />
        <p className="metric-label">Magnitud regional estimada</p>
        <strong className="metric-value">
          {magnitude.value == null ? 'No disponible' : `≈ ${number(magnitude.value, 2)}`}
        </strong>
        <p className="metric-note">{magnitude.reason}</p>
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
        Alcance regional · corte de observación: {weekLabel(summary.semana_corte)} · objetivo:{' '}
        {weekLabel(summary.semana_objetivo)} · actualización de la API:{' '}
        {date(summary.fecha_actualizacion)}
        {targetStarted(summary.semana_objetivo)
          ? ' · Semana objetivo iniciada; consulta histórica.'
          : ''}
      </div>
    </div>
  );
}
