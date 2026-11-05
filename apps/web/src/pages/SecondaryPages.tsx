import { AppLink, Card, Empty } from '../components/ui';

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
