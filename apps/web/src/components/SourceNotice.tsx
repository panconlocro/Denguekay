import { dataSource } from '../lib/dataSource';
import { date } from '../lib/format';

export function SourceNotice({
  source,
  verified,
  cutoff,
}: {
  source: ReturnType<typeof dataSource>;
  verified: boolean;
  cutoff?: string | null;
}) {
  const [title, description] =
    source === 'fixtures'
      ? [
          'Entorno de pruebas · muestra v0',
          'Incluye valores alterados para probar la interfaz. No representa resultados de v2.',
        ]
      : source === 'demo-v2'
        ? verified
          ? [
              'Demo local v2 · experimental',
              'Datos agregados de Piura y predicciones del ajuste local. Consulta el corte y la semana objetivo; no son alertas operativas.',
            ]
          : ['Demo local · conexión pendiente de verificar', 'Comprobando las versiones de la API.']
        : source === 'api'
          ? ['API configurada', 'Versiones, disponibilidad y fechas informadas por el servicio.']
          : [
              'Fuente sin identificar',
              'Identifica la fuente de datos de este entorno antes de compartirlo.',
            ];
  return (
    <aside className="source-notice" aria-label="Procedencia de los datos" role="note">
      <strong>{title}</strong>
      <p>{description}</p>
      {source === 'demo-v2' && verified && <p>Corte de datos: {date(cutoff)}.</p>}
    </aside>
  );
}
