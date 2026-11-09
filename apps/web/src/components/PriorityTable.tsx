import { useState } from 'react';
import type { District, Prediction } from '../api/types';
import { number, percent } from '../lib/format';
import { AppLink, RiskChip } from './ui';

const pageSize = 9;

export function PriorityTable({ rows, districts }: { rows: Prediction[]; districts: District[] }) {
  const [requestedPage, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const page = Math.min(requestedPage, pages);
  const offset = (page - 1) * pageSize;
  const visible = rows.slice(offset, offset + pageSize);
  return (
    <>
      <div
        className="table-scroll"
        role="region"
        aria-label="Listado de distritos prioritarios"
        tabIndex={0}
      >
        <table className="priorities">
          <caption className="sr-only">
            Distritos ordenados por probabilidad descendente; empates por UBIGEO.
          </caption>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Distrito</th>
              <th scope="col">Probabilidad de brote</th>
              <th scope="col">Nivel</th>
              <th scope="col">Casos est.</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((p, i) => (
              <tr key={p.ubigeo}>
                <td>{offset + i + 1}</td>
                <td>
                  <AppLink to={`/distritos/${p.ubigeo}`}>
                    <strong>{p.distrito}</strong>
                  </AppLink>
                  <small>
                    Prov. {districts.find((d) => d.ubigeo === p.ubigeo)?.provincia || 'Sin dato'}
                  </small>
                </td>
                <td>
                  <div className="probability">
                    {p.probabilidad_brote != null && (
                      <span
                        className={`probability-track risk-${p.nivel_riesgo}`}
                        aria-hidden="true"
                      >
                        <i style={{ width: `${p.probabilidad_brote * 100}%` }} />
                      </span>
                    )}
                    <strong>{percent(p.probabilidad_brote)}</strong>
                  </div>
                </td>
                <td>
                  <RiskChip level={p.nivel_riesgo} label={p.nivel_riesgo_etiqueta} />
                </td>
                <td>
                  {p.casos_estimados == null ? 'Sin datos' : `≈ ${number(p.casos_estimados, 2)}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="footnote" role="status">
        Se muestran {visible.length} de {rows.length} distritos con predicción disponible.{' '}
        Posiciones {offset + 1}–{offset + visible.length}. Los casos son estimaciones para la semana
        objetivo.
      </p>
      {pages > 1 && (
        <nav className="pagination" aria-label="Páginas de distritos prioritarios">
          <span>
            Página {page} de {pages}
          </span>
          <button className="button" disabled={page === 1} onClick={() => setPage(page - 1)}>
            Anterior
          </button>
          <button className="button" disabled={page === pages} onClick={() => setPage(page + 1)}>
            Siguiente
          </button>
        </nav>
      )}
    </>
  );
}
