import { Component } from 'react';
import type { ReactNode } from 'react';

export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="standalone-error">
        <div className="card failure" role="alert">
          <h1>No se pudo abrir esta vista</h1>
          <p>
            Ocurrió un problema al cargar la aplicación. Recarga para volver a consultar el
            servicio.
          </p>
          <button className="button primary" onClick={() => window.location.reload()}>
            Recargar aplicación
          </button>
        </div>
      </main>
    );
  }
}
