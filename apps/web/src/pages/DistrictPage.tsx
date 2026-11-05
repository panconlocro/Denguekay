import { Link, useOutletContext, useParams, useSearchParams } from 'react-router-dom';
import type { AppContext } from '../App';
import type { Configuration, District, Prediction } from '../api/types';
import { useDistrictAlerts, useDistrictPrediction, useObservations } from '../api/queries';
import { SeriesChartView } from '../components/Visuals';
import { PublicationNotice } from '../components/PublicationNotice';
import { Card, DataTag, Empty, Failure, Loading, RiskChip } from '../components/ui';
import { districtPath, intervalText } from '../lib/district';
import { date, number, percent, weekLabel } from '../lib/format';

export function DistrictPage() {
  const route = useParams();
  const context = useOutletContext<AppContext>();
  const id = route.ubigeo || context.district;
  const selected = context.districts.find((d) => d.ubigeo === id);
  if (context.cataloguePending)
    return (
      <Card>
        <Loading label="Cargando catálogo distrital" />
      </Card>
    );
  if (!context.catalogueReady)
    return (
      <Card>
        <Empty title="Catálogo distrital no disponible">Reintenta la consulta del catálogo.</Empty>
      </Card>
    );
  if (id && !selected)
    return (
      <Card>
        <Empty title="Distrito no encontrado">
          El código no pertenece al catálogo cargado de Piura.
        </Empty>
      </Card>
    );
  if (selected) return <DistrictDetail district={selected} context={context} />;
  const catalogue = context.districts.filter(
    (d) => !context.province || d.ubigeo_provincia === context.province,
  );
  return (
    <Card
      title="Detalle y series temporales"
      subtitle="Selecciona un distrito de la provincia elegida para consultar sus resultados."
    >
      {!catalogue.length ? (
        <Empty title="Sin distritos para esta selección">
          Revisa la provincia o utiliza «Limpiar filtros».
        </Empty>
      ) : (
        <div className="district-catalogue">
          {catalogue.map((d) => (
            <Link
              key={d.ubigeo}
              to={districtPath(
                `/distritos/${d.ubigeo}`,
                context.search,
                d.ubigeo,
                d.ubigeo_provincia,
                context.horizon,
              )}
            >
              <strong>{d.nombre}</strong>
              <small>
                {d.provincia} · {d.ubigeo} →
              </small>
            </Link>
          ))}
        </div>
      )}
    </Card>
  );
}

function DistrictDetail({ district, context }: { district: District; context: AppContext }) {
  const { horizon, enabled, configuration, search } = context;
  const query = useDistrictPrediction(district.ubigeo, horizon, enabled);
  const prediction =
    query.isError || !enabled || !query.data?.disponible
      ? undefined
      : query.data.elementos.find((p) => p.ubigeo === district.ubigeo && p.horizonte === horizon);
  const available = prediction?.disponible && prediction.estado === 'disponible';
  const cut =
    prediction?.semana_corte ||
    configuration.horizontes.find((h) => h.horizonte === horizon)?.semana_corte_vigente;
  const observed = useObservations(district.ubigeo, cut?.fecha_inicio, cut?.fecha_inicio, !!cut);
  const observation =
    observed.isError || !observed.data?.disponible
      ? undefined
      : observed.data.elementos.find(
          (o) => o.ubigeo === district.ubigeo && o.semana.id_semana === cut?.id_semana,
        );
  const mapParams = new URLSearchParams(search);
  mapParams.delete('distrito');
  mapParams.set('seleccion', district.ubigeo);
  return (
    <>
      <div className="district-heading">
        <div>
          <h2 className="view-title">
            {district.nombre} · {district.provincia}
          </h2>
          <p className="muted">UBIGEO {district.ubigeo} · resultados por semana epidemiológica</p>
        </div>
        <Link className="text-link" to={`/mapa?${mapParams}`}>
          Ver en el mapa →
        </Link>
      </div>
      {available && <PublicationNotice rows={[prediction]} scopeLabel={district.nombre} />}
      <div className="district-overview">
        <div className="detail-indicators">
          {!enabled ? (
            <Card>
              <Empty title="Horizonte no disponible">
                {configuration.horizontes.find((h) => h.horizonte === horizon)?.motivo}
              </Empty>
            </Card>
          ) : query.isError ? (
            <Card>
              <Failure error={query.error} retry={() => void query.refetch()} />
            </Card>
          ) : query.isPending ? (
            <Card>
              <Loading label="Cargando pronóstico distrital" />
            </Card>
          ) : !available ? (
            <Card>
              <Empty title="Predicción distrital no disponible">
                {prediction?.motivo ||
                  query.data?.motivo ||
                  'Sin predicción publicada para este distrito y horizonte.'}
              </Empty>
            </Card>
          ) : (
            <>
              <Card>
                <DataTag />
                <p className="metric-label">Probabilidad de brote</p>
                <strong className="metric-value">{percent(prediction.probabilidad_brote)}</strong>
                <RiskChip
                  level={prediction.nivel_riesgo}
                  label={prediction.nivel_riesgo_etiqueta}
                />
                <p className="metric-note">
                  {weekLabel(prediction.semana_objetivo)} ·{' '}
                  {prediction.experimental ? 'Experimental' : 'Modelo validado'}
                </p>
              </Card>
              <Card>
                <DataTag />
                <p className="metric-label">Magnitud estimada</p>
                <strong className="metric-value">
                  {prediction.casos_estimados == null
                    ? 'No disponible'
                    : `≈ ${number(prediction.casos_estimados, 2)} casos`}
                </strong>
                <p className="metric-note">
                  {intervalText(prediction)
                    ? `${intervalText(prediction)}. Rango orientativo, no calibrado.`
                    : prediction.motivo_intervalo || 'Sin intervalo publicado.'}
                </p>
                <p className="metric-note">
                  Umbral de la semana objetivo: no publicado por la API.
                </p>
              </Card>
            </>
          )}
        </div>
        <Card
          title="Pronóstico por horizonte"
          subtitle="Cada fila conserva su propia semana objetivo"
        >
          <div
            className="table-scroll"
            role="region"
            aria-label="Pronóstico por horizonte"
            tabIndex={0}
          >
            <table className="horizon-comparison">
              <thead>
                <tr>
                  <th>Horizonte</th>
                  <th>Objetivo</th>
                  <th>Probabilidad / nivel</th>
                  <th>Casos est.</th>
                </tr>
              </thead>
              <tbody>
                {configuration.horizontes.map((h) => (
                  <HorizonRow key={h.horizonte} district={district} item={h} current={horizon} />
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
      {enabled && (
        <Card
          title="Serie temporal de casos"
          subtitle="Observado, pronosticado y umbral histórico publicado · rangos ajustables"
        >
          <SeriesChartView ubigeo={district.ubigeo} horizon={horizon} />
        </Card>
      )}
      <div className="district-bottom">
        <Card title="Contexto observado en el corte" subtitle={weekLabel(cut)}>
          {!cut ? (
            <Empty title="Corte no disponible" />
          ) : observed.isError ? (
            <Failure error={observed.error} retry={() => void observed.refetch()} />
          ) : observed.isPending ? (
            <Loading label="Cargando observación del corte" />
          ) : !observation ? (
            <Empty title="Observación no disponible">
              No hay una observación publicada para este distrito en el corte del pronóstico.
            </Empty>
          ) : (
            <>
              <DataTag observed />
              <dl className="district-facts">
                <dt>Casos observados</dt>
                <dd>{number(observation.casos_dengue)}</dd>
                <dt>Umbral observado en el corte</dt>
                <dd>
                  {observation.umbral_brote_casos == null
                    ? 'No disponible'
                    : `${number(observation.umbral_brote_casos, 2)} casos`}
                </dd>
                <dt>Temperatura media</dt>
                <dd>
                  {observation.temp_media_c == null
                    ? 'No disponible'
                    : `${number(observation.temp_media_c, 2)} °C`}
                </dd>
                <dt>Humedad relativa media</dt>
                <dd>
                  {observation.hum_rel_media_pct == null
                    ? 'No disponible'
                    : `${number(observation.hum_rel_media_pct, 2)} %`}
                </dd>
                <dt>Precipitación total</dt>
                <dd>
                  {observation.precip_total_mm == null
                    ? 'No disponible'
                    : `${number(observation.precip_total_mm, 2)} mm`}
                </dd>
                <dt>Fuente epidemiológica</dt>
                <dd>
                  {observation.fuente_casos === 'sala_situacional'
                    ? 'Sala situacional'
                    : 'Histórico epidemiológico'}
                </dd>
                <dt>Cobertura</dt>
                <dd>
                  {
                    {
                      verificado: 'Verificada',
                      sin_registro: 'Sin registro',
                      pendiente: 'Pendiente',
                    }[observation.estado_cobertura]
                  }
                </dd>
              </dl>
              <p className="footnote">
                Valores de la semana de corte; no son agregados de variables ni explicaciones
                individuales del modelo. El umbral observado no se extrapola al objetivo.{' '}
                {observation.estado_cobertura !== 'verificado' &&
                  'Un cero sin cobertura verificada no certifica ausencia de casos.'}
              </p>
            </>
          )}
        </Card>
        <div className="stack">
          <AssociatedAlerts
            district={district}
            horizon={horizon}
            prediction={available ? prediction : undefined}
            search={search}
          />
          <Card title="Alcance de la interpretación">
            <p className="muted">
              La API no expone contribuciones individuales ni agregados de vecinos para este
              distrito. Las variables observadas y las importancias globales describen asociaciones;
              no se interpretan como causas.
            </p>
            <Link className="text-link" to={`/modelo${search}`}>
              Ver desempeño del modelo →
            </Link>
          </Card>
        </div>
      </div>
    </>
  );
}

function HorizonRow({
  district,
  item,
  current,
}: {
  district: District;
  item: Configuration['horizontes'][number];
  current: number;
}) {
  const query = useDistrictPrediction(district.ubigeo, item.horizonte, item.disponible);
  const [params, setParams] = useSearchParams();
  const p =
    query.isError || !query.data?.disponible
      ? undefined
      : query.data.elementos.find(
          (p) =>
            p.ubigeo === district.ubigeo &&
            p.horizonte === item.horizonte &&
            p.disponible &&
            p.estado === 'disponible',
        );
  const choose = () => {
    const next = new URLSearchParams(params);
    next.set('horizonte', String(item.horizonte));
    setParams(next);
  };
  return (
    <tr aria-current={current === item.horizonte ? 'true' : undefined}>
      <th scope="row">
        <button
          className="horizon-select"
          aria-pressed={current === item.horizonte}
          onClick={choose}
        >
          {item.horizonte} semanas
        </button>
        <small>
          {!item.disponible ? 'No disponible' : item.experimental ? 'Experimental' : 'Validado'}
        </small>
      </th>
      {!item.disponible ? (
        <td colSpan={3}>{item.motivo || 'Sin modelo disponible.'}</td>
      ) : query.isError ? (
        <td colSpan={3}>
          <Failure error={query.error} retry={() => void query.refetch()} />
        </td>
      ) : query.isPending ? (
        <td colSpan={3}>Cargando…</td>
      ) : !p ? (
        <td colSpan={3}>{query.data?.motivo || 'Sin predicción distrital disponible.'}</td>
      ) : (
        <>
          <td>{weekLabel(p.semana_objetivo)}</td>
          <td>
            {percent(p.probabilidad_brote)}
            <RiskChip level={p.nivel_riesgo} label={p.nivel_riesgo_etiqueta} />
          </td>
          <td>
            {p.casos_estimados == null ? 'No disponible' : `≈ ${number(p.casos_estimados, 2)}`}
          </td>
        </>
      )}
    </tr>
  );
}

function AssociatedAlerts({
  district,
  horizon,
  prediction,
  search,
}: {
  district: District;
  horizon: number;
  prediction?: Prediction;
  search: string;
}) {
  const query = useDistrictAlerts(district.ubigeo, horizon, !!prediction);
  const rows =
    query.isError || !query.data?.disponible
      ? undefined
      : query.data.elementos.filter(
          (a) =>
            a.ubigeo === district.ubigeo &&
            a.prediccion.semana_objetivo.id_semana === prediction?.semana_objetivo.id_semana,
        );
  return (
    <Card
      title={prediction?.experimental ? 'Avisos experimentales asociados' : 'Alertas asociadas'}
    >
      {!prediction ? (
        <Empty title="Sin pronóstico disponible">
          No se comprueba la asociación sin una semana objetivo publicada.
        </Empty>
      ) : query.isError ? (
        <Failure error={query.error} retry={() => void query.refetch()} />
      ) : query.isPending ? (
        <Loading label="Consultando avisos del distrito" />
      ) : !rows ? (
        <Empty>{query.data?.motivo}</Empty>
      ) : !rows.length ? (
        <p className="muted">Sin avisos activos para este distrito y semana objetivo.</p>
      ) : (
        rows.map((a) => (
          <article key={a.id_alerta} className="associated-alert">
            <RiskChip level={a.nivel} label={a.nivel_etiqueta} />
            <p>
              {weekLabel(a.prediccion.semana_objetivo)} · generado {date(a.fecha_generacion)}
            </p>
            <p>
              {a.experimental
                ? 'Aviso experimental; no es una alerta operativa.'
                : 'Registro publicado por la API.'}
            </p>
          </article>
        ))
      )}
      <Link
        className="button full-width"
        to={districtPath('/alertas', search, district.ubigeo, district.ubigeo_provincia, horizon)}
      >
        Consultar registros del distrito →
      </Link>
    </Card>
  );
}
