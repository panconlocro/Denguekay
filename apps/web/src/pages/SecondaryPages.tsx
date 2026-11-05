import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import type { AppContext } from '../App';
import { get } from '../api/client';
import { useAlerts } from '../api/queries';
import { AppLink, Card, Empty, Failure, Loading, RiskChip } from '../components/ui';
import { date, percent, riskRange, weekLabel } from '../lib/format';

export function AlertsPage() {
  const { horizon, enabled, province, district, districts, configuration } =
    useOutletContext<AppContext>();
  const [state, setState] = useState('activa');
  const [page, setPage] = useState(1);
  const query = useAlerts(horizon, enabled, state);
  const experimental = configuration.horizontes.find((h) => h.horizonte === horizon)?.experimental;
  const rows = (query.isError ? [] : query.data?.elementos || []).filter(
    (a) =>
      (!district || a.ubigeo === district) &&
      (!province || districts.find((d) => d.ubigeo === a.ubigeo)?.ubigeo_provincia === province),
  );
  const visiblePage = Math.min(page, Math.max(1, Math.ceil(rows.length / 10)));
  if (!enabled)
    return (
      <Card>
        <Empty title="Horizonte no disponible" />
      </Card>
    );
  return (
    <Card
      title={experimental ? 'Avisos experimentales' : 'Alertas tempranas'}
      subtitle="Registros publicados por la API. No se recalcula el nivel de riesgo en el navegador."
      action={
        <label className="inline-select">
          Estado{' '}
          <select
            aria-label="Estado de los avisos"
            value={state}
            onChange={(e) => {
              setState(e.target.value);
              setPage(1);
            }}
          >
            <option value="activa">Activos</option>
            <option value="retirada">Retirados</option>
          </select>
        </label>
      }
    >
      {query.isError ? (
        <Failure error={query.error} retry={() => void query.refetch()} />
      ) : query.isPending ? (
        <Loading />
      ) : !rows.length ? (
        <Empty title="Sin registros para esta selección" />
      ) : (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Nivel</th>
                  <th>Distrito</th>
                  <th>Probabilidad</th>
                  <th>Semana objetivo</th>
                  <th>Generado</th>
                  <th>Cambio</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.slice((visiblePage - 1) * 10, visiblePage * 10).map((a) => (
                  <tr key={a.id_alerta}>
                    <td>
                      <RiskChip level={a.nivel} label={a.nivel_etiqueta} />
                    </td>
                    <td>
                      <strong>{a.distrito}</strong>
                    </td>
                    <td>{percent(a.prediccion.probabilidad_brote)}</td>
                    <td>{weekLabel(a.prediccion.semana_objetivo)}</td>
                    <td>{date(a.fecha_generacion)}</td>
                    <td>
                      {a.estado === 'retirada'
                        ? a.motivo || 'Retirada'
                        : {
                            nueva: 'Nueva',
                            se_mantiene: 'Se mantiene',
                            sube_nivel: 'Sube de nivel',
                            baja_nivel: 'Baja de nivel',
                          }[a.cambio]}
                    </td>
                    <td>
                      <AppLink to={`/distritos/${a.ubigeo}`} className="text-link">
                        Ver detalle →
                      </AppLink>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <span>
              {rows.length} registros · página {visiblePage} de {Math.ceil(rows.length / 10)}
            </span>
            <button disabled={visiblePage === 1} onClick={() => setPage(visiblePage - 1)}>
              Anterior
            </button>
            <button
              disabled={visiblePage * 10 >= rows.length}
              onClick={() => setPage(visiblePage + 1)}
            >
              Siguiente
            </button>
          </div>
        </>
      )}
      <p className="footnote">
        {experimental
          ? 'Son avisos experimentales de un modelo no validado; no generan notificaciones.'
          : 'La regla operativa y los niveles proceden de la API.'}
      </p>
    </Card>
  );
}

export function ModelsPage() {
  const { horizon } = useOutletContext<AppContext>();
  const models = useQuery({
    queryKey: ['models', horizon],
    queryFn: ({ signal }) => get('/api/v1/modelos/activo', { horizonte: horizon }, signal),
  });
  return (
    <Card
      title="Versiones del modelo en uso"
      subtitle="Trazabilidad del clasificador y regresor para el horizonte seleccionado"
    >
      {models.isError ? (
        <Failure error={models.error} retry={() => void models.refetch()} />
      ) : !models.data ? (
        <Loading />
      ) : !models.data.elementos.length ? (
        <Empty>{models.data.motivo}</Empty>
      ) : (
        <>
          <p className="scope-note">{models.data.nota}</p>
          <div className="model-grid">
            {models.data.elementos.map((m) => (
              <article className="model-tile" key={m.id_version}>
                <span className="eyebrow">
                  {m.tarea === 'clasificacion' ? 'PROBABILIDAD DE BROTE' : 'MAGNITUD DE CASOS'}
                </span>
                <h3>{m.codigo}</h3>
                <dl>
                  <dt>Algoritmo</dt>
                  <dd>{m.algoritmo}</dd>
                  <dt>Horizonte</dt>
                  <dd>{m.horizonte} semanas</dd>
                  <dt>Estado</dt>
                  <dd>{m.experimental ? 'Experimental · no validado' : 'Validado'}</dd>
                  <dt>Registro</dt>
                  <dd>{date(m.fecha_registro)}</dd>
                </dl>
              </article>
            ))}
          </div>
          <p className="footnote">
            La comparación de métricas por bloque y las importancias se incorporarán en la entrega
            de desempeño. Esta vista inicial muestra las versiones reales, sin cifras ilustrativas.
          </p>
        </>
      )}
    </Card>
  );
}

export function HelpPage() {
  const { configuration } = useOutletContext<AppContext>();
  return (
    <Card title="Ayuda e interpretación de resultados" subtitle="Guía inicial de la aplicación">
      <div className="help-content">
        <h3>Observado y pronosticado</h3>
        <p>
          Los casos observados son datos publicados por las fuentes epidemiológicas. Los
          pronosticados son estimaciones del modelo para una semana objetivo; no son casos
          confirmados.
        </p>
        <h3>Probabilidad y nivel de riesgo</h3>
        <p>
          La probabilidad estima si los casos superarán el umbral de brote distrital. El color
          siempre se acompaña de una etiqueta. «Sin datos» no equivale a riesgo bajo.
        </p>
        <ul>
          {configuration.leyenda.map((l) => (
            <li key={l.nivel || 'none'}>
              {l.etiqueta}: {riskRange(l.desde, l.hasta)}
            </li>
          ))}
        </ul>
        <h3>Horizonte y vigencia</h3>
        <p>
          El horizonte indica semanas entre el corte de datos y la semana objetivo. Una semana
          objetivo pasada se identifica como consulta histórica: el último corte publicado no
          necesariamente es un pronóstico actual.
        </p>
        <h3>Modo experimental</h3>
        <p>
          Una predicción disponible puede provenir de un modelo no validado. Se rotula como
          experimental y sus avisos no son alertas operativas ni generan notificaciones.
        </p>
        <h3>Datos ausentes y errores</h3>
        <p>
          Los valores ausentes se muestran como «No disponible». Las series se interrumpen en los
          huecos y no se sustituyen por cero. Si falla una consulta, usa «Reintentar».
        </p>
        <h3>Mapa y filtros</h3>
        <p>
          Los puntos actuales son centroides distritales, no límites territoriales. Los filtros
          geográficos afectan al mapa y los listados; los indicadores superiores del tablero
          conservan su alcance regional.
        </p>
        <h3>Soporte y manual</h3>
        <p>
          El canal de soporte, el PDF del manual y los materiales de capacitación están pendientes
          de publicación.
        </p>
      </div>
    </Card>
  );
}

export function NotFoundPage() {
  return (
    <Card>
      <Empty title="Página no encontrada">Revisa la dirección o vuelve al tablero.</Empty>
      <AppLink to="/" className="button primary">
        Volver al tablero
      </AppLink>
    </Card>
  );
}
