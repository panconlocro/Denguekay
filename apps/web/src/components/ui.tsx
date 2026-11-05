import { createContext, useContext, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import type { RiskLevel } from '../api/types';
import { ApiError } from '../api/client';

const StateHeadingLevel = createContext<2 | 3>(2);

export function AppLink({
  to,
  children,
  className,
}: {
  to: string;
  children: ReactNode;
  className?: string;
}) {
  const { search } = useLocation();
  return (
    <Link to={`${to}${search}`} className={className}>
      {children}
    </Link>
  );
}

export function Icon({ name }: { name: string }) {
  if (name === 'grid')
    return (
      <span className="grid-icon" aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
      </span>
    );
  if (name === 'bars')
    return (
      <span className="bars-icon" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
    );
  return (
    <span className={`nav-icon ${name === 'help' ? 'help-icon' : ''}`} aria-hidden="true">
      <img src={`/assets/${name === 'help' ? 'help-ring' : name}.svg`} alt="" />
      {name === 'help' && <b>?</b>}
      {name === 'alert' && <b>!</b>}
    </span>
  );
}

export function RiskChip({ level, label }: { level: RiskLevel | null; label?: string | null }) {
  return (
    <span className={`risk-chip risk-${level || 'missing'}`}>
      <i />
      {label || 'Sin datos'}
    </span>
  );
}

export function DataTag({ observed = false }: { observed?: boolean }) {
  return (
    <span className={`data-tag ${observed ? 'observed' : 'forecast'}`}>
      {observed ? 'OBSERVADO' : 'PRONOSTICADO'}
    </span>
  );
}

export function Card({
  title,
  subtitle,
  action,
  children,
  className = '',
}: {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {title && (
        <div className="card-heading">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      <StateHeadingLevel.Provider value={title ? 3 : 2}>{children}</StateHeadingLevel.Provider>
    </section>
  );
}

export function Loading({ label = 'Consultando información' }: { label?: string }) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="spinner" />
      <p>{label}…</p>
      <div className="skeleton" />
      <div className="skeleton short" />
      <div className="skeleton" />
    </div>
  );
}

export function Empty({
  title = 'No disponible',
  children,
  headingLevel,
}: {
  title?: string;
  children?: ReactNode;
  headingLevel?: 2 | 3;
}) {
  const contextLevel = useContext(StateHeadingLevel);
  const Heading = (headingLevel ?? contextLevel) === 2 ? 'h2' : 'h3';
  return (
    <div className="empty">
      <span className="empty-symbol" aria-hidden="true">
        —
      </span>
      <Heading>{title}</Heading>
      <p>{children || 'No hay información publicada para esta selección.'}</p>
    </div>
  );
}

export function Failure({
  error,
  retry,
  headingLevel,
}: {
  error: Error;
  retry: () => void;
  headingLevel?: 2 | 3;
}) {
  const contextLevel = useContext(StateHeadingLevel);
  const Heading = (headingLevel ?? contextLevel) === 2 ? 'h2' : 'h3';
  return (
    <div className="failure" role="alert">
      <div className="failure-icon" aria-hidden="true">
        !
      </div>
      <Heading>No se pudo cargar la información</Heading>
      <p>{error.message}</p>
      {error instanceof ApiError && (
        <small>
          HTTP {error.status} · {error.code}
        </small>
      )}
      <p>Los datos anteriores no se presentan como vigentes.</p>
      <button className="button primary" onClick={retry}>
        Reintentar
      </button>
    </div>
  );
}
