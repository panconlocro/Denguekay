import { useOutletContext, useSearchParams } from 'react-router-dom';
import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { AppContext } from '../App';
import type { Model, ModelDetail } from '../api/types';
import { useModels, useModelDetail, useModelVariables } from '../api/queries';
import { Card, Empty, Failure, Loading } from '../components/ui';
import { number, date } from '../lib/format';
import {
  baselineRatio,
  blockIds,
  blockLabel,
  blocks,
  importances,
  metrics,
  record,
  selectedModel,
  textValue,
  valueAt,
} from '../lib/modelMetrics';
import '../models.css';

const unavailable = 'No disponible';
function score(value: number | null) {
  return number(value, 3);
}
function taskLabel(task: Model['tarea']) {
  return task === 'clasificacion' ? 'Clasificador' : 'Regresor';
}
function QueryContent({
  query,
  missing,
  children,
}: {
  query: UseQueryResult<ModelDetail>;
  missing: boolean;
  children: ReactNode;
}) {
  return missing ? (
    <Empty title="Versión no disponible">No hay una versión única publicada para esta tarea.</Empty>
  ) : query.isError ? (
    <Failure error={query.error} retry={() => void query.refetch()} />
  ) : !query.data ? (
    <Loading />
  ) : (
    children
  );
}

export function ModelsPage() {
  const { horizon, configuration, enabled } = useOutletContext<AppContext>();
  const [search, setSearch] = useSearchParams();
  const models = useModels(horizon, enabled);
  const selected = !enabled || models.isError ? [] : models.data?.elementos || [];
  const clf = selectedModel(selected, 'clasificacion');
  const reg = selectedModel(selected, 'regresion');
  const classification = useModelDetail(clf?.id_version);
  const regression = useModelDetail(reg?.id_version);
  const cData = classification.isError ? undefined : classification.data;
  const rData = regression.isError ? undefined : regression.data;
  const periods = blockIds(cData, rData);
  const block = search.get('modelo_bloque') || periods[0] || '';
  const validBlock = periods.includes(block);
  const c = metrics(cData, block);
  const r = metrics(rData, block);
  const change = (key: string, value: string) => {
    const next = new URLSearchParams(search);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearch(next);
  };

  return (
    <div className="performance-page">
      <div className="performance-heading">
        <div>
          <span className="eyebrow">EVALUACIÓN Y TRAZABILIDAD</span>
          <h2>Desempeño del modelo</h2>
          <p>Resultados publicados por versión, horizonte y bloque temporal.</p>
        </div>
        <label className="period-control">
          Bloque de evaluación
          <select
            aria-label="Bloque de evaluación"
            value={block}
            onChange={(e) => change('modelo_bloque', e.target.value)}
            disabled={!periods.length}
          >
            {!periods.length && <option value="">Sin bloques publicados</option>}
            {!!block && !validBlock && <option value={block}>Bloque no publicado: {block}</option>}
            {periods.map((p) => (
              <option key={p} value={p}>
                {blockLabel(p)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="scope-note">
        Evaluación del conjunto de distritos; los filtros geográficos no recalculan estas métricas.
        Cada bloque conserva su período: no se promedian años ni horizontes.
      </p>
      {!enabled ? (
        <Card>
          <Empty title="Modelo no disponible para este horizonte">
            No hay un par de modelos disponible para {horizon} semanas. Selecciona otro horizonte
            para consultar su evaluación.
          </Empty>
          <div className="model-alternatives">
            {configuration.horizontes
              .filter((h) => h.disponible)
              .map((h) => (
                <button
                  className="button"
                  key={h.horizonte}
                  onClick={() => change('horizonte', String(h.horizonte))}
                >
                  Ver desempeño a {h.horizonte} semanas
                </button>
              ))}
          </div>
        </Card>
      ) : models.isError ? (
        <Failure error={models.error} retry={() => void models.refetch()} />
      ) : !models.data ? (
        <Loading />
      ) : (
        <>
          <Card
            title="Versiones en uso"
            subtitle={`${horizon} semanas · selección publicada por la API`}
          >
            {!selected.length ? (
              <Empty>{models.data.motivo}</Empty>
            ) : (
              <div className="model-grid">
                {selected.map((m) => (
                  <article className="model-tile" key={m.id_version}>
                    <span className="eyebrow">{taskLabel(m.tarea)}</span>
                    <h3>{m.codigo}</h3>
                    <p>
                      {m.algoritmo} · ID {m.id_version} · {m.estado}
                    </p>
                    <dl>
                      <dt>Selección de servicio</dt>
                      <dd>{m.seleccion === 'experimental' ? 'Experimental' : 'Activa'}</dd>
                      <dt>Aceptación de esta versión</dt>
                      <dd>
                        {m.cumple_umbrales
                          ? 'Cumple umbrales publicados'
                          : 'No cumple umbrales publicados'}
                      </dd>
                      <dt>Registro</dt>
                      <dd>{date(m.fecha_registro)}</dd>
                    </dl>
                  </article>
                ))}
              </div>
            )}
            <p className="footnote">
              La aceptación individual no convierte el par servido en operativo. El bloque
              seleccionado no cambia la decisión de aceptación registrada por la API; sus umbrales
              numéricos no están expuestos aquí.
            </p>
          </Card>
          {!validBlock && periods.length > 0 && (
            <Card>
              <Empty title="Bloque no publicado">
                Selecciona un bloque disponible para consultar sus métricas.
              </Empty>
              <button className="button" onClick={() => change('modelo_bloque', '')}>
                Usar último bloque publicado
              </button>
            </Card>
          )}
          <Card
            title="Clasificación de brotes"
            subtitle={`${clf?.codigo || 'Sin clasificador'} · ${validBlock ? blockLabel(block) : 'Sin bloque disponible'}`}
          >
            <QueryContent query={classification} missing={!clf}>
              {!c.available ? (
                <Empty>No se publicaron métricas de este bloque para el clasificador.</Empty>
              ) : (
                <>
                  <div className="classification-metrics">
                    {(
                      [
                        ['Recall', c.recall, 'Proporción de semanas con brote detectadas.'],
                        [
                          'Precisión',
                          c.precision,
                          'Proporción de avisos que correspondieron a brotes.',
                        ],
                        ['F1', c.f1, 'Balance entre precisión y recall.'],
                        ['AUC-PR', c.auprc, 'Área bajo la curva precisión-recall.'],
                      ] as const
                    ).map(([label, value, note]) => (
                      <article className="metric-tile" key={label}>
                        <h3>{label}</h3>
                        <strong className="metric-value">{score(value)}</strong>
                        <p>{note}</p>
                      </article>
                    ))}
                  </div>
                  <p className="footnote">
                    Filas evaluadas: {number(c.n)} · Positivos: {number(c.positives)} · Umbral de
                    probabilidad del bloque: {score(c.threshold)}. Escala de métricas: 0 a 1. Un
                    valor ausente no es cero.
                  </p>
                </>
              )}
            </QueryContent>
          </Card>
          <Card
            title="Magnitud frente a persistencia"
            subtitle={`${reg?.codigo || 'Sin regresor'} · ${validBlock ? blockLabel(block) : 'Sin bloque disponible'}`}
          >
            <QueryContent query={regression} missing={!reg}>
              {!r.available ? (
                <Empty>No se publicaron métricas de este bloque para el regresor.</Empty>
              ) : (
                <>
                  <div className="table-scroll">
                    <table className="baseline-table">
                      <caption className="sr-only">
                        Error de conteos del regresor y la persistencia
                      </caption>
                      <thead>
                        <tr>
                          <th>Métrica</th>
                          <th>Modelo</th>
                          <th>Persistencia</th>
                          <th>% del error de persistencia</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(
                          [
                            ['MAE', r.mae, r.baselineMae],
                            ['RMSE', r.rmse, r.baselineRmse],
                          ] as const
                        ).map(([label, value, baseline]) => {
                          const ratio = baselineRatio(value, baseline);
                          return (
                            <tr key={label}>
                              <th scope="row">
                                {label} <span className="footnote">(casos)</span>
                              </th>
                              <td>{score(value)}</td>
                              <td>{score(baseline)}</td>
                              <td>{ratio === null ? unavailable : `${number(ratio, 1)} %`}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <p className="footnote">
                    Filas evaluadas: {number(r.n)}. Menor MAE o RMSE indica menor error; una razón
                    inferior al 100 % indica menos error que persistencia en ese bloque. Con
                    persistencia cero la razón no está definida. Esta comparación no determina por
                    sí sola la aceptación.
                  </p>
                  {c.n !== null && r.n !== null && c.n !== r.n && (
                    <p className="scope-note">
                      Los tamaños de evaluación difieren entre tareas; no se asume que comparten las
                      mismas filas.
                    </p>
                  )}
                </>
              )}
            </QueryContent>
          </Card>
          <Card
            title="Comparación por horizonte"
            subtitle={`Mismo bloque: ${validBlock ? blockLabel(block) : 'Sin bloque disponible'} · versiones en uso de cada horizonte`}
          >
            <div className="table-scroll">
              <table className="horizon-performance">
                <caption className="sr-only">
                  Métricas y versiones por horizonte del mismo bloque temporal
                </caption>
                <thead>
                  <tr>
                    <th>Horizonte y selección</th>
                    <th>Clasificador / Regresor</th>
                    <th>Recall</th>
                    <th>Precisión</th>
                    <th>F1</th>
                    <th>AUC-PR</th>
                    <th>MAE</th>
                    <th>RMSE</th>
                  </tr>
                </thead>
                <tbody>
                  {configuration.horizontes.map((h) => (
                    <HorizonRow
                      key={h.horizonte}
                      horizon={h.horizonte}
                      enabled={h.disponible}
                      block={validBlock ? block : ''}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <div className="performance-bottom">
            <Card
              title="Importancia de variables"
              subtitle="Valores publicados por versión; no implican causalidad"
            >
              <label>
                Versión para importancias
                <select
                  aria-label="Versión para importancias"
                  value={search.get('modelo_importancia') || (reg ? 'regresion' : 'clasificacion')}
                  onChange={(e) => change('modelo_importancia', e.target.value)}
                >
                  {search.get('modelo_importancia') &&
                    !['regresion', 'clasificacion'].includes(search.get('modelo_importancia')!) && (
                      <option value={search.get('modelo_importancia')!}>Selección no válida</option>
                    )}
                  <option value="regresion">Regresor</option>
                  <option value="clasificacion">Clasificador</option>
                </select>
              </label>
              <Variables
                model={selectedModel(
                  selected,
                  (search.get('modelo_importancia') ||
                    (reg ? 'regresion' : 'clasificacion')) as Model['tarea'],
                )}
              />
            </Card>
            <Card
              title="Protocolo temporal y reproducibilidad"
              subtitle="La evaluación por bloques es distinta del ajuste para servir predicciones"
            >
              {(
                [
                  ['Clasificador', clf, classification],
                  ['Regresor', reg, regression],
                ] as const
              ).map(([label, model, query]) => (
                <section className="model-provenance" key={label}>
                  <h3>
                    {label} · {model?.codigo || unavailable}
                  </h3>
                  <QueryContent query={query} missing={!model}>
                    {query.data && !query.isError && (
                      <Provenance detail={query.data} block={block} />
                    )}
                  </QueryContent>
                </section>
              ))}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function HorizonRow({
  horizon,
  enabled,
  block,
}: {
  horizon: number;
  enabled: boolean;
  block: string;
}) {
  const models = useModels(horizon, enabled);
  const selected = !enabled || models.isError ? [] : models.data?.elementos || [];
  const clf = selectedModel(selected, 'clasificacion');
  const reg = selectedModel(selected, 'regresion');
  const cQuery = useModelDetail(clf?.id_version);
  const rQuery = useModelDetail(reg?.id_version);
  const c = metrics(cQuery.isError ? undefined : cQuery.data, block);
  const r = metrics(rQuery.isError ? undefined : rQuery.data, block);
  if (!enabled || models.isError || !models.data || !selected.length)
    return (
      <tr>
        <th scope="row">{horizon} semanas</th>
        <td colSpan={7}>
          {!enabled ? (
            unavailable
          ) : models.isError ? (
            <button className="button" onClick={() => void models.refetch()}>
              Reintentar horizonte {horizon}
            </button>
          ) : !models.data ? (
            'Cargando…'
          ) : (
            unavailable
          )}
        </td>
      </tr>
    );
  return (
    <tr>
      <th scope="row">
        {horizon} semanas
        <small>
          {selected.some((m) => m.seleccion === 'experimental')
            ? 'Selección experimental'
            : 'Selección activa'}
        </small>
      </th>
      <td className="version-cell">
        <div>{clf?.codigo || unavailable}</div>
        <div>{reg?.codigo || unavailable}</div>
        {cQuery.isError && (
          <button className="button" onClick={() => void cQuery.refetch()}>
            Reintentar clasificador h{horizon}
          </button>
        )}
        {rQuery.isError && (
          <button className="button" onClick={() => void rQuery.refetch()}>
            Reintentar regresor h{horizon}
          </button>
        )}
        {((cQuery.isPending && clf) || (rQuery.isPending && reg)) && (
          <span>Cargando métricas…</span>
        )}
      </td>
      {[c.recall, c.precision, c.f1, c.auprc, r.mae, r.rmse].map((value, i) => (
        <td key={i}>{score(value)}</td>
      ))}
    </tr>
  );
}

function Variables({ model }: { model?: Model }) {
  const query = useModelVariables(model?.id_version);
  if (!model)
    return (
      <Empty title="Versión no disponible">Elige una tarea con una versión única publicada.</Empty>
    );
  if (query.isError) return <Failure error={query.error} retry={() => void query.refetch()} />;
  if (!query.data) return <Loading />;
  const rows = importances(query.data.elementos);
  const maximum = Math.max(...rows.map((row) => row.importance), 0);
  return (
    <div className="importance-data">
      <p>
        <strong>{model.codigo}</strong>
      </p>
      <p className="scope-note">
        {query.data.nota || 'La API no especifica el método de importancia.'}
      </p>
      {!rows.length ? (
        <Empty title="Sin importancias publicadas">
          No hay valores numéricos válidos para esta versión.
        </Empty>
      ) : (
        <>
          <p className="footnote">
            Valores originales; la longitud de las barras es relativa al máximo de esta versión. No
            representan porcentajes ni cambian con el bloque de evaluación.
          </p>
          <ol className="importance-list">
            {rows.map((row) => (
              <li key={`${row.rank}-${row.variable}`}>
                <div>
                  <span>
                    {row.rank}. {row.variable}
                  </span>
                  <strong>{number(row.importance, 5)}</strong>
                </div>
                <div className="importance-track" aria-hidden="true">
                  <span
                    style={{ width: `${maximum > 0 ? (100 * row.importance) / maximum : 0}%` }}
                  />
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
      {rows.length !== query.data.elementos.length && (
        <p className="scope-note">Se omitieron entradas sin nombre, rango o importancia válidos.</p>
      )}
    </div>
  );
}

function Provenance({ detail, block }: { detail: ModelDetail; block: string }) {
  const repro = record(detail.reproducibilidad);
  const publishedBlock = record(blocks(detail)[block]);
  const temporal = Object.keys(publishedBlock).length
    ? record(valueAt(repro, 'particion_temporal', 'bloques', block))
    : {};
  const source = textValue(detail.metricas.procedencia);
  const rows = [
    ['Inicio del ajuste de servicio', repro.entrenamiento_inicio],
    ['Corte del ajuste de servicio', repro.entrenamiento_corte],
    ['Calibración', repro.calibracion],
    ['Intervalo', repro.intervalo],
    ['Corte de entrenamiento del bloque', publishedBlock.corte_ajuste ?? temporal.corte_ajuste],
    [
      'Primera semana objetivo del bloque',
      publishedBlock.primera_semana_objetivo ?? temporal.primera_semana_objetivo,
    ],
    [
      'Última semana objetivo del bloque',
      publishedBlock.ultima_semana_objetivo ?? temporal.ultima_semana_objetivo,
    ],
  ];
  return (
    <>
      <p>{source || 'Procedencia de las métricas no publicada.'}</p>
      <dl className="provenance-facts">
        {rows.map(([label, value]) => (
          <div key={String(label)}>
            <dt>{String(label)}</dt>
            <dd>{textValue(value) || unavailable}</dd>
          </div>
        ))}
      </dl>
      <p className="footnote">
        Las fechas ausentes de cada bloque no se deducen de su nombre ni de las fechas del ajuste de
        servicio.
      </p>
      <details>
        <summary>Ver ficha técnica y huellas</summary>
        <dl className="provenance-facts">
          <div>
            <dt>MLflow run</dt>
            <dd>{detail.mlflow_run_id}</dd>
          </div>
          <div>
            <dt>SHA-256 del artefacto</dt>
            <dd>{detail.sha256_artefacto}</dd>
          </div>
          <div>
            <dt>SHA-256 del dataset</dt>
            <dd>{detail.sha256_dataset}</dd>
          </div>
        </dl>
        <h4>Hiperparámetros publicados</h4>
        <pre>{JSON.stringify(detail.hiperparametros, null, 2)}</pre>
        <h4>Reproducibilidad publicada</h4>
        <pre>{JSON.stringify(repro, null, 2)}</pre>
      </details>
    </>
  );
}
