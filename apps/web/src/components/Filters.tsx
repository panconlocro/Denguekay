import type { Configuration, District, Week } from '../api/types';
import { horizonStatus, weekLabel } from '../lib/format';

export function Filters({
  configuration,
  districts,
  horizon,
  province,
  district,
  target,
  change,
  reset,
}: {
  configuration: Configuration;
  districts: District[];
  horizon: number;
  province: string;
  district: string;
  target?: Week | null;
  change: (key: string, value: string) => void;
  reset: () => void;
}) {
  const provinces = [...new Map(districts.map((d) => [d.ubigeo_provincia, d.provincia])).entries()];
  return (
    <section className="filters" aria-label="Filtros de consulta">
      <label className="select-field">
        <span>PROVINCIA</span>
        <select
          aria-label="Provincia"
          value={province}
          onChange={(e) => change('provincia', e.target.value)}
        >
          <option value="">Todas</option>
          {province && !provinces.some(([id]) => id === province) && (
            <option value={province}>Provincia no reconocida ({province})</option>
          )}
          {provinces.map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <label className="select-field district-filter">
        <span>DISTRITO</span>
        <select
          aria-label="Distrito"
          value={district}
          onChange={(e) => change('distrito', e.target.value)}
        >
          <option value="">Todos</option>
          {district &&
            !districts.some(
              (d) => d.ubigeo === district && (!province || d.ubigeo_provincia === province),
            ) && <option value={district}>Distrito fuera de selección ({district})</option>}
          {districts
            .filter((d) => !province || d.ubigeo_provincia === province)
            .map((d) => (
              <option key={d.ubigeo} value={d.ubigeo}>
                {d.nombre}
              </option>
            ))}
        </select>
      </label>
      <fieldset className="horizon-field">
        <legend>HORIZONTE DE PRONÓSTICO</legend>
        <div className="segments">
          {configuration.horizontes.map((h) => (
            <button
              key={h.horizonte}
              aria-pressed={horizon === h.horizonte}
              onClick={() => change('horizonte', String(h.horizonte))}
              title={h.motivo || undefined}
            >
              <strong>{h.horizonte} semanas</strong>
              <small
                className={
                  h.experimental ? 'experimental-text' : h.disponible ? 'operational-text' : ''
                }
              >
                ● {horizonStatus(h)}
              </small>
            </button>
          ))}
        </div>
      </fieldset>
      <div className="select-field target-field">
        <span>SEMANA OBJETIVO</span>
        <strong>{weekLabel(target)}</strong>
        <small>Corte publicado para este horizonte</small>
      </div>
      <div className="filter-summary">
        <span>FILTROS APLICADOS</span>
        <strong>
          {districts.find((d) => d.ubigeo === district)?.nombre ||
            provinces.find(([id]) => id === province)?.[1] ||
            'Región Piura'}{' '}
          · h = {horizon} semanas
        </strong>
        <button onClick={reset}>Limpiar filtros</button>
      </div>
    </section>
  );
}
