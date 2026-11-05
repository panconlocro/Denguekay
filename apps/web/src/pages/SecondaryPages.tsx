import { useQuery } from '@tanstack/react-query';
import { useOutletContext } from 'react-router-dom';
import type { AppContext } from '../App';
import { get } from '../api/client';
import { AppLink, Card, Empty, Failure, Loading } from '../components/ui';
import { date, riskRange } from '../lib/format';

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
