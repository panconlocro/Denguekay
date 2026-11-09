import { useMemo } from 'react';
import { Link, useOutletContext, useSearchParams } from 'react-router-dom';
import type { AppContext } from '../App';
import { useRiskMap } from '../api/queries';
import { RiskMapView } from '../components/Visuals';
import { Card, DataTag, Empty, Failure, Loading, RiskChip } from '../components/ui';
import { inSelection } from '../lib/dashboard';
import { districtPath, intervalText, mapCounts } from '../lib/district';
import { date, number, percent, weekLabel } from '../lib/format';

export function MapPage() {
  const {
    horizon,
    enabled,
    province,
    district,
    districts,
    search,
    catalogueReady,
    cataloguePending,
  } = useOutletContext<AppContext>();
  const query = useRiskMap(horizon, enabled);
  const [params, setParams] = useSearchParams();
  const selectedId = district || params.get('seleccion') || '';
  const data = query.isError ? undefined : query.data;
  const visible = useMemo(
    () =>
      data
        ? {
            ...data,
            features: data.features.filter((f) => inSelection(f.id, districts, province, district)),
          }
        : undefined,
    [data, districts, province, district],
  );
  const selected = visible?.features.find((f) => f.id === selectedId);
  const select = (id: string) => {
    const next = new URLSearchParams(params);
    if (id) next.set('seleccion', id);
    else next.delete('seleccion');
    setParams(next);
  };
  if (!enabled)
    return (
      <Card>
        <Empty title="Horizonte no disponible" />
      </Card>
    );
  if (cataloguePending)
    return (
      <Card>
        <Loading label="Cargando catálogo geográfico" />
      </Card>
    );
  if (!catalogueReady)
    return (
      <Card>
        <Empty title="Catálogo geográfico no disponible">
          Reintenta la consulta del catálogo para consultar el mapa.
        </Empty>
      </Card>
    );
  if (query.isError)
    return (
      <Card>
        <Failure error={query.error} retry={() => void query.refetch()} />
      </Card>
    );
  if (!visible)
    return (
      <Card>
        <Loading label="Cargando mapa distrital" />
      </Card>
    );
  if (!visible.features.length)
    return (
      <Card>
        <Empty title="Sin distritos para esta selección">
          {visible.motivo || 'Revisa provincia y distrito o utiliza «Limpiar filtros».'}
        </Empty>
      </Card>
    );
  const missing = visible.features.filter(
    (f) => f.properties.estado !== 'disponible' || f.properties.nivel_riesgo == null,
  );
  const counts = mapCounts(visible);
  const p = selected?.properties;
  const available = p?.estado === 'disponible';
  const provinceId = districts.find((d) => d.ubigeo === selectedId)?.ubigeo_provincia || '';
  return (
    <>
      <p className="scope-note">
        {weekLabel(visible.semana_objetivo)} · objetivo{' '}
        {date(visible.semana_objetivo?.fecha_inicio)} – {date(visible.semana_objetivo?.fecha_fin)} ·
        corte {weekLabel(visible.semana_corte)}. Selecciona un marcador o usa el selector del panel.
      </p>
      <div className="map-layout">
        <Card
          title="Mapa de riesgo distrital"
          subtitle="Centroides distritales · selección con clic, Enter o barra espaciadora"
          className="map-main"
        >
          <RiskMapView data={visible} select={select} selected={selectedId} />
          <p className="footnote">
            {visible.features.length} distritos representados. Los puntos no delimitan el
            territorio; la leyenda procede de la API.
          </p>
        </Card>
        <div className="stack">
          <Card title="Distrito seleccionado">
            <label className="panel-select">
              Distrito del panel
              <select
                aria-label="Distrito del panel"
                value={selected?.id || ''}
                onChange={(e) => select(e.target.value)}
                disabled={!!district}
              >
                <option value="">Selecciona un distrito</option>
                {visible.features.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.properties.distrito} · {f.id}
                  </option>
                ))}
              </select>
            </label>
            {!p ? (
              <Empty
                title={selectedId ? 'Distrito fuera de la selección' : 'Selecciona un distrito'}
              >
                El panel muestra el riesgo y la magnitud del distrito elegido, sin salir del mapa.
              </Empty>
            ) : (
              <>
                <h3 className="selected-district-name">{p.distrito}</h3>
                <p className="muted">
                  {p.provincia} · UBIGEO {p.ubigeo}
                </p>
                <div
                  className={`selected-risk risk-${available ? p.nivel_riesgo || 'missing' : 'missing'}`}
                >
                  <DataTag />
                  <p>Probabilidad de brote</p>
                  <strong>{available ? percent(p.probabilidad_brote) : 'Sin datos'}</strong>
                  <RiskChip
                    level={available ? p.nivel_riesgo : null}
                    label={available ? p.nivel_riesgo_etiqueta : 'Sin datos'}
                  />
                </div>
                <dl className="district-facts">
                  <dt>Magnitud estimada</dt>
                  <dd>
                    {available && p.casos_estimados != null
                      ? `≈ ${number(p.casos_estimados, 2)} casos`
                      : 'No disponible'}
                  </dd>
                  <dt>Intervalo</dt>
                  <dd>{available && intervalText(p) ? intervalText(p) : 'No disponible'}</dd>
                  <dt>Semana objetivo</dt>
                  <dd>{weekLabel(visible.semana_objetivo)}</dd>
                  <dt>Horizonte</dt>
                  <dd>
                    {horizon} semanas · {p.experimental ? 'Experimental' : 'Validado'}
                  </dd>
                  <dt>Actualización de la API</dt>
                  <dd>{date(visible.fecha_actualizacion)}</dd>
                </dl>
                {!available && (
                  <p className="scope-note">
                    {p.motivo || 'Este distrito no tiene una predicción disponible.'}
                  </p>
                )}
                {available && intervalText(p) && (
                  <p className="footnote">Intervalo orientativo, no calibrado.</p>
                )}
                <div className="panel-actions">
                  <Link
                    className="button primary full-width"
                    to={districtPath(
                      `/distritos/${p.ubigeo}`,
                      search,
                      p.ubigeo,
                      provinceId,
                      horizon,
                    )}
                  >
                    Ver detalle y serie temporal →
                  </Link>
                  <Link
                    className="button full-width"
                    to={districtPath('/alertas', search, p.ubigeo, provinceId, horizon)}
                  >
                    Ver {p.experimental ? 'avisos' : 'alertas'} del distrito →
                  </Link>
                </div>
              </>
            )}
          </Card>
          <Card title={`Distritos por nivel · ${weekLabel(visible.semana_objetivo)}`}>
            <div className="risk-distribution">
              {counts.map((level) => (
                <div key={level.nivel || 'missing'} className={`risk-${level.nivel || 'missing'}`}>
                  <RiskChip level={level.nivel} label={level.etiqueta} />
                  <span className="distribution-track" aria-hidden="true">
                    <i style={{ width: `${(100 * level.count) / visible.features.length}%` }} />
                  </span>
                  <strong>{level.count}</strong>
                </div>
              ))}
            </div>
            <p className="footnote">
              Recuento de los {visible.features.length} distritos representados con los filtros
              actuales.
            </p>
          </Card>
          <Card title="Distritos sin predicción" className="unavailable-card">
            {!missing.length ? (
              <p className="muted">
                Todos los distritos representados tienen un nivel de riesgo publicado.
              </p>
            ) : (
              <ul className="missing-districts">
                {missing.map((f) => (
                  <li key={f.id}>
                    <button onClick={() => select(f.id)}>{f.properties.distrito}</button>
                    <p>{f.properties.motivo || 'Sin nivel de riesgo disponible.'}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
