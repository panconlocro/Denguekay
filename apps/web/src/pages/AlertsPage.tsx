import {
  Link,
  Navigate,
  useLocation,
  useOutletContext,
  useParams,
  useSearchParams,
} from 'react-router-dom';
import type { AppContext } from '../App';
import type { Alert } from '../api/types';
import { ApiError } from '../api/client';
import { useAlert, useAlerts } from '../api/queries';
import { Card, DataTag, Empty, Failure, Loading, RiskChip } from '../components/ui';
import { PublicationNotice } from '../components/PublicationNotice';
import {
  alertChanges,
  alertContextSearch,
  alertExperimental,
  alertFilters,
  alertProbability,
  selectAlerts,
  sortAlerts,
} from '../lib/alerts';
import { districtPath, intervalText } from '../lib/district';
import { dateTime, number, percent, targetStarted, weekLabel } from '../lib/format';

const pageSize = 10;

export function AlertsPage() {
  const context = useOutletContext<AppContext>();
  const {
    horizon,
    enabled,
    province,
    district,
    districts,
    configuration,
    catalogueReady,
    cataloguePending,
  } = context;
  const [params, setParams] = useSearchParams();
  const filters = alertFilters(params);
  const validGeography =
    (!province || districts.some((d) => d.ubigeo_provincia === province)) &&
    (!district ||
      districts.some(
        (d) => d.ubigeo === district && (!province || d.ubigeo_provincia === province),
      ));
  const canRead = catalogueReady && validGeography && !filters.error;
  const active = useAlerts(horizon, canRead, 'activa');
  const retired = useAlerts(horizon, canRead, 'retirada');
  const subset = (rows: Alert[], state: Alert['estado']) =>
    sortAlerts(
      selectAlerts(
        rows,
        state,
        horizon,
        districts,
        province,
        district,
        filters.level,
        filters.week,
      ),
      filters.order,
    );
  const activeRows =
    active.isError || !active.data?.disponible
      ? undefined
      : subset(active.data.elementos, 'activa');
  const retiredRows =
    retired.isError || !retired.data?.disponible
      ? undefined
      : subset(retired.data.elementos, 'retirada');
  const query = filters.state === 'activa' ? active : retired;
  const rows = filters.state === 'activa' ? activeRows : retiredRows;
  const experimental = configuration.horizontes.find((h) => h.horizonte === horizon)?.experimental;
  const weeks = [
    ...new Map(
      [
        ...(active.isError ? [] : active.data?.elementos || []),
        ...(retired.isError ? [] : retired.data?.elementos || []),
      ].map((a) => [String(a.prediccion.semana_objetivo.id_semana), a.prediccion.semana_objetivo]),
    ).entries(),
  ].sort(([a], [b]) => b.localeCompare(a));
  const pages = Math.max(1, Math.ceil((rows?.length || 0) / pageSize));
  const page = Math.min(filters.page, pages);
  const visible = rows?.slice((page - 1) * pageSize, page * pageSize) || [];
  const change = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('aviso_pagina');
    setParams(next);
  };
  const reset = () => {
    const next = new URLSearchParams(params);
    for (const key of [...next.keys()]) if (key.startsWith('aviso_')) next.delete(key);
    setParams(next);
  };
  const goPage = (value: number) => {
    const next = new URLSearchParams(params);
    next.set('aviso_pagina', String(value));
    setParams(next);
  };
  if (cataloguePending)
    return (
      <Card>
        <Loading label="Cargando catálogo para filtrar avisos" />
      </Card>
    );
  if (!catalogueReady)
    return (
      <Card>
        <Empty title="Catálogo no disponible">
          Reintenta el catálogo para consultar los registros por distrito.
        </Empty>
      </Card>
    );
  if (!validGeography)
    return (
      <Card>
        <Empty title="Selección geográfica no válida">
          Revisa provincia y distrito o utiliza «Limpiar filtros».
        </Empty>
      </Card>
    );
  if (filters.error)
    return (
      <Card>
        <Empty title="Filtros de avisos no válidos">
          Revisa el estado, nivel, orden, semana y página indicados en la dirección.
        </Empty>
        <button className="button primary" onClick={reset}>
          Restablecer filtros de avisos
        </button>
      </Card>
    );
  return (
    <>
      {!enabled && (
        <Card>
          <Empty title="Horizonte sin modelo disponible">
            Se consulta únicamente el historial publicado para h = {horizon}; no hay nuevos
            pronósticos disponibles para este horizonte.
          </Empty>
        </Card>
      )}
      <p className="scope-note">
        Registros publicados para h = {horizon} ·{' '}
        {districts.find((d) => d.ubigeo === district)?.nombre ||
          districts.find((d) => d.ubigeo_provincia === province)?.provincia ||
          'Región Piura'}
        . «Activo» es el estado del registro: su semana objetivo puede haber comenzado. Cada fila
        conserva su propio objetivo.
      </p>
      <Card title="Filtros de avisos">
        <div className="alert-filters">
          <label>
            Estado
            <select
              aria-label="Estado de los avisos"
              value={filters.state}
              onChange={(e) => change('aviso_estado', e.target.value)}
            >
              <option value="activa">Activos</option>
              <option value="retirada">Retirados</option>
            </select>
          </label>
          <label>
            Nivel
            <select
              aria-label="Nivel de los avisos"
              value={filters.level}
              onChange={(e) => change('aviso_nivel', e.target.value)}
            >
              <option value="">Alto y Muy alto</option>
              <option value="alto">Alto</option>
              <option value="muy_alto">Muy alto</option>
            </select>
          </label>
          <label>
            Ordenar por
            <select
              aria-label="Orden de los avisos"
              value={filters.order}
              onChange={(e) => change('aviso_orden', e.target.value)}
            >
              <option value="riesgo">Nivel y probabilidad</option>
              <option value="probabilidad">Probabilidad descendente</option>
              <option value="fecha">Generación más reciente</option>
            </select>
          </label>
          <label>
            Semana objetivo
            <select
              aria-label="Semana objetivo de los avisos"
              value={filters.week}
              onChange={(e) => change('aviso_semana', e.target.value)}
            >
              <option value="">Todas las publicadas</option>
              {filters.week && !weeks.some(([id]) => id === filters.week) && (
                <option value={filters.week}>Semana {filters.week} · sin registros cargados</option>
              )}
              {weeks.map(([id, week]) => (
                <option key={id} value={id}>
                  {weekLabel(week)}
                </option>
              ))}
            </select>
          </label>
          <button className="button" onClick={reset}>
            Restablecer filtros de avisos
          </button>
        </div>
      </Card>
      <div className="alert-indicators" role="group" aria-label="Resumen de registros filtrados">
        <Card>
          <p className="metric-label">Registros activos</p>
          <strong className="metric-value">{number(activeRows?.length)}</strong>
          <p className="metric-note">
            {activeRows
              ? `${activeRows.filter((a) => a.nivel === 'muy_alto').length} Muy alto · ${activeRows.filter((a) => a.nivel === 'alto').length} Alto`
              : 'Consulta pendiente o no disponible.'}
          </p>
        </Card>
        <Card>
          <p className="metric-label">Activos marcados «Nueva»</p>
          <strong className="metric-value">
            {number(activeRows?.filter((a) => a.cambio === 'nueva').length)}
          </strong>
          <p className="metric-note">
            Entre los activos filtrados; no es un recuento de esta actualización.
          </p>
        </Card>
        <Card>
          <p className="metric-label">Registros retirados</p>
          <strong className="metric-value">{number(retiredRows?.length)}</strong>
          <p className="metric-note">Historial filtrado completo, no solo el último lote.</p>
        </Card>
        <Card className="unavailable-card">
          <p className="metric-label">Próxima actualización</p>
          <strong className="metric-value muted">No disponible</strong>
          <p className="metric-note">No hay una fecha de publicación confirmada.</p>
        </Card>
      </div>
      <div id="alerts-list" tabIndex={-1}>
        <Card
          title={
            filters.state === 'retirada'
              ? 'Registros retirados'
              : experimental
                ? 'Avisos experimentales'
                : 'Alertas publicadas'
          }
          subtitle="Orden aplicado a todos los registros cargados antes de paginar; niveles conservados tal como fueron publicados."
        >
          {query.isError ? (
            <Failure error={query.error} retry={() => void query.refetch()} />
          ) : query.isPending ? (
            <Loading label="Cargando todos los registros de avisos" />
          ) : !rows ? (
            <Empty title="Registros no disponibles">{query.data?.motivo}</Empty>
          ) : !rows.length ? (
            <Empty title="Sin registros para esta selección">
              No hay registros publicados que cumplan estos filtros.
            </Empty>
          ) : (
            <>
              <div
                className="table-scroll"
                role="region"
                aria-label="Listado de avisos"
                tabIndex={0}
              >
                <table className="alerts-table">
                  <caption className="sr-only">
                    Registro completo filtrado por estado, geografía, nivel, horizonte y semana
                    objetivo.
                  </caption>
                  <thead>
                    <tr>
                      <th>Nivel guardado</th>
                      <th>Distrito</th>
                      <th>Probabilidad vinculada</th>
                      <th>Semana objetivo</th>
                      <th>Generación / retiro</th>
                      <th>Cambio registrado</th>
                      <th>Estado</th>
                      <th>Detalle</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((a) => (
                      <AlertRow key={a.id_alerta} alert={a} search={`?${params}`} />
                    ))}
                  </tbody>
                </table>
              </div>
              <nav className="pagination" aria-label="Páginas de avisos">
                <span role="status">
                  {rows.length} registros · página {page} de {pages} · posiciones{' '}
                  {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, rows.length)}
                </span>
                <button disabled={page === 1} onClick={() => goPage(page - 1)}>
                  Anterior
                </button>
                <button disabled={page === pages} onClick={() => goPage(page + 1)}>
                  Siguiente
                </button>
              </nav>
            </>
          )}
        </Card>
      </div>
      <div className="alerts-bottom">
        <Card
          title="Historial de retirados"
          subtitle="Vista previa de hasta tres registros de esta selección"
        >
          {retired.isError ? (
            <Failure error={retired.error} retry={() => void retired.refetch()} />
          ) : retired.isPending ? (
            <Loading label="Cargando historial de retiros" />
          ) : !retiredRows ? (
            <Empty>{retired.data?.motivo}</Empty>
          ) : !retiredRows.length ? (
            <Empty title="Sin retiros publicados" />
          ) : (
            <ul className="retired-preview">
              {sortAlerts(retiredRows, 'fecha')
                .slice(0, 3)
                .map((a) => (
                  <li key={a.id_alerta}>
                    <strong>{a.distrito}</strong>
                    <RiskChip level={a.nivel} label={a.nivel_etiqueta} />
                    <p>Retiro: {dateTime(a.fecha_retiro)}</p>
                    <p>{a.motivo || 'Motivo de retiro no publicado.'}</p>
                    <Link
                      className="text-link"
                      to={`/alertas/${a.id_alerta}?${params}`}
                      state={{ from: `/alertas?${params}` }}
                    >
                      Abrir retiro #{a.id_alerta} →
                    </Link>
                  </li>
                ))}
            </ul>
          )}
          {!!retiredRows?.length && (
            <button
              className="button"
              onClick={() => {
                change('aviso_estado', 'retirada');
                document.getElementById('alerts-list')?.focus();
              }}
            >
              Ver todos los retirados
            </button>
          )}
        </Card>
        <Card title="Cómo interpretar estos registros" className="alert-rule">
          <p>
            La regla actual utiliza los niveles Alto y Muy alto: probabilidad a partir de{' '}
            {percent(configuration.cortes_riesgo.alto)}. El nivel guardado y el motivo de retiro se
            conservan como historial.
          </p>
          <p>
            Los cambios «Nueva», «Se mantiene», «Sube de nivel» y «Baja de nivel» describen cada
            registro. No identifican por sí solos un lote de actualización.
          </p>
          <p>
            Los avisos experimentales no son alertas operativas ni generan notificaciones. Un
            registro activo con objetivo iniciado se consulta como histórico.
          </p>
        </Card>
      </div>
    </>
  );
}

function AlertRow({ alert: a, search }: { alert: Alert; search: string }) {
  return (
    <tr className={a.estado === 'retirada' ? 'retired-record' : 'active-record'}>
      <td data-label="Nivel guardado">
        <RiskChip level={a.nivel} label={a.nivel_etiqueta} />
      </td>
      <td data-label="Distrito">
        <strong>{a.distrito}</strong>
        <small>{a.ubigeo}</small>
        <span className={alertExperimental(a) ? 'experimental-record-tag' : 'record-tag'}>
          {alertExperimental(a) ? 'Experimental' : 'Validación informada por el servicio'}
        </span>
      </td>
      <td data-label="Probabilidad vinculada">{percent(alertProbability(a))}</td>
      <td data-label="Semana objetivo">
        {weekLabel(a.prediccion.semana_objetivo)}
        <small>h = {a.horizonte} semanas</small>
        {targetStarted(a.prediccion.semana_objetivo) && (
          <small>Objetivo iniciado · histórico</small>
        )}
      </td>
      <td data-label="Generación / retiro">
        {dateTime(a.fecha_generacion)}
        {a.estado === 'retirada' && (
          <>
            <small>Retiro: {dateTime(a.fecha_retiro)}</small>
            <small>{a.motivo || 'Motivo no publicado.'}</small>
          </>
        )}
      </td>
      <td data-label="Cambio registrado">
        <span className={`change-tag change-${a.cambio}`}>{alertChanges[a.cambio]}</span>
      </td>
      <td data-label="Estado">
        <span className={`record-state state-${a.estado}`}>
          {a.estado === 'activa' ? 'Activo en el registro' : 'Retirado'}
        </span>
      </td>
      <td data-label="Detalle">
        <Link
          className="text-link"
          to={`/alertas/${a.id_alerta}${search}`}
          state={{ from: `/alertas${search}` }}
        >
          Ver detalle →
        </Link>
      </td>
    </tr>
  );
}

export function AlertDetailPage() {
  const { id: rawId } = useParams();
  const id = Number(rawId);
  const validId = !!rawId && /^[1-9]\d*$/.test(rawId) && Number.isSafeInteger(id);
  const { districts, catalogueReady, cataloguePending } = useOutletContext<AppContext>();
  const location = useLocation();
  const query = useAlert(id, validId);
  if (!validId)
    return (
      <Card>
        <Empty title="Identificador de aviso no válido" />
        <Link className="button" to="/alertas">
          Volver al listado
        </Link>
      </Card>
    );
  if (query.isError)
    return (
      <Card>
        {query.error instanceof ApiError && query.error.status === 404 ? (
          <Empty title="Registro no encontrado">
            El servicio no tiene un aviso con este identificador.
          </Empty>
        ) : (
          <Failure error={query.error} retry={() => void query.refetch()} />
        )}
        <Link className="button" to={`/alertas${location.search}`}>
          Volver al listado
        </Link>
      </Card>
    );
  if (query.isPending || cataloguePending)
    return (
      <Card>
        <Loading label="Cargando detalle del registro" />
      </Card>
    );
  if (!catalogueReady)
    return (
      <Card>
        <Empty title="Catálogo no disponible">
          Reintenta el catálogo para identificar el distrito del aviso.
        </Empty>
      </Card>
    );
  const a = query.data;
  const p = a.prediccion;
  if (a.ubigeo !== p.ubigeo || a.horizonte !== p.horizonte)
    return (
      <Card>
        <Empty title="Registro incoherente">
          El distrito y horizonte del aviso no coinciden con su predicción vinculada.
        </Empty>
      </Card>
    );
  const canonical = alertContextSearch(a, location.search, districts);
  if (canonical !== location.search)
    return <Navigate to={`/alertas/${id}${canonical}`} replace state={location.state} />;
  const available = p.disponible && p.estado === 'disponible';
  const source = location.state?.from;
  const back =
    typeof source === 'string' && (source === '/alertas' || source.startsWith('/alertas?'))
      ? source
      : `/alertas?horizonte=${a.horizonte}&aviso_estado=${a.estado}`;
  const province = districts.find((d) => d.ubigeo === a.ubigeo)?.ubigeo_provincia || '';
  return (
    <>
      <div className="district-heading">
        <div>
          <h2 className="view-title">
            {alertExperimental(a) ? 'Aviso experimental' : 'Registro de alerta'} #{a.id_alerta} ·{' '}
            {a.distrito}
          </h2>
          <p className="scope-note">
            {a.estado === 'retirada' ? 'Retirado' : 'Activo en el registro'} ·{' '}
            {weekLabel(p.semana_objetivo)}
            {targetStarted(p.semana_objetivo) ? ' · Objetivo iniciado: consulta histórica' : ''}
          </p>
        </div>
        <Link className="button" to={back}>
          Volver al listado
        </Link>
      </div>
      <Card
        className={alertExperimental(a) ? 'experimental-alert-detail' : ''}
        title="Estado y trazabilidad del registro"
      >
        <RiskChip level={a.nivel} label={a.nivel_etiqueta} />
        <dl className="district-facts">
          <dt>Estado guardado</dt>
          <dd>{a.estado === 'retirada' ? 'Retirado' : 'Activo'}</dd>
          <dt>Cambio registrado</dt>
          <dd>{alertChanges[a.cambio]}</dd>
          <dt>Generación del registro</dt>
          <dd>{dateTime(a.fecha_generacion)}</dd>
          <dt>Retiro</dt>
          <dd>{a.estado === 'retirada' ? dateTime(a.fecha_retiro) : 'Sin retiro registrado'}</dd>
          <dt>Motivo</dt>
          <dd>{a.motivo || 'No publicado'}</dd>
          <dt>UBIGEO</dt>
          <dd>{a.ubigeo}</dd>
          <dt>Predicción vinculada</dt>
          <dd>
            #{p.id_prediccion} · ejecución #{p.id_ejecucion}
          </dd>
          <dt>Versiones vinculadas</dt>
          <dd>
            Clasificador{' '}
            {p.id_version_clasificador == null ? 'no informado' : `#${p.id_version_clasificador}`} ·
            regresor {p.id_version_regresor == null ? 'no informado' : `#${p.id_version_regresor}`}
          </dd>
        </dl>
        {alertExperimental(a) && (
          <p className="scope-note">
            Registro experimental: no constituye una alerta operativa ni genera notificaciones.
          </p>
        )}
      </Card>
      {available && <PublicationNotice rows={[p]} scopeLabel={a.distrito} />}
      <div className="detail-indicators alert-detail-values">
        <Card title="Predicción vinculada">
          <DataTag />
          <p className="metric-label">Probabilidad publicada en la predicción</p>
          <strong className="metric-value">
            {available ? percent(p.probabilidad_brote) : 'Sin datos'}
          </strong>
          <RiskChip
            level={available ? p.nivel_riesgo : null}
            label={available ? p.nivel_riesgo_etiqueta : 'Sin datos'}
          />
          <p className="metric-note">
            {weekLabel(p.semana_objetivo)} · corte {weekLabel(p.semana_corte)} · emisión{' '}
            {dateTime(p.fecha_generacion)}
          </p>
        </Card>
        <Card title="Magnitud vinculada">
          <DataTag />
          <strong className="metric-value">
            {available && p.casos_estimados != null
              ? `≈ ${number(p.casos_estimados, 2)} casos`
              : 'No disponible'}
          </strong>
          <p className="metric-note">
            {available && intervalText(p)
              ? `${intervalText(p)}. Rango orientativo, no calibrado.`
              : p.motivo_intervalo || p.motivo || 'Intervalo no disponible.'}
          </p>
        </Card>
      </div>
      <Card title="Alcance del historial">
        <p className="muted">
          El nivel guardado del aviso y la predicción vinculada son datos distintos. En un retiro,
          la predicción puede haber sido actualizada: no se dispone de una instantánea anterior para
          reconstruir una transición de probabilidad.
        </p>
        <p className="footnote">
          El detalle distrital consulta el último corte publicado, que puede ser diferente al de
          este registro.
        </p>
        <div className="alert-detail-links">
          <Link
            className="button primary"
            to={districtPath(`/distritos/${a.ubigeo}`, canonical, a.ubigeo, province, a.horizonte)}
          >
            Ver distrito en el último corte →
          </Link>
          <Link
            className="button"
            to={districtPath('/mapa', canonical, a.ubigeo, province, a.horizonte)}
          >
            Ver distrito en el mapa →
          </Link>
        </div>
      </Card>
    </>
  );
}
