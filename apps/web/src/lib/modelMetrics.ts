import type { Model, ModelDetail } from '../api/types';
import { date, number } from './format';

export function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function valueAt(value: unknown, ...path: string[]): unknown {
  return path.reduce<unknown>((node, key) => record(node)[key], value);
}

export function finite(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
}

function probability(value: unknown) {
  const valid = finite(value);
  return valid !== null && valid <= 1 ? valid : null;
}

export function textValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

export function selectedModel(models: Model[], task: Model['tarea']) {
  const matches = models.filter((m) => m.tarea === task);
  return matches.length === 1 ? matches[0] : undefined;
}

export function blocks(detail?: ModelDetail) {
  return record(detail?.metricas.bloques);
}

// Keep periods separate. Unrecognized names remain selectable, after dated blocks.
export function blockIds(...details: (ModelDetail | undefined)[]) {
  return [...new Set(details.flatMap((d) => Object.keys(blocks(d))))].sort((a, b) => {
    const year = (id: string) => Number(id.match(/(?:^|_)(\d{4})(?:_|$)/)?.[1] || 0);
    return year(b) - year(a) || a.localeCompare(b);
  });
}

export function blockLabel(id: string) {
  const pooled = id.match(/^temporadas_(\d{4})_(\d{4})$/);
  if (pooled) return `Temporadas ${pooled[1]}–${pooled[2]} (aceptación)`;
  return id.replace(/^temporada_/, 'Temporada ').replace(/^calendario_/, 'Calendario ');
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
function shownDate(value: string | null) {
  return value && ISO_DATE.test(value) ? date(value) : value;
}

// Rows of the temporal protocol that the version publishes. What it does not publish is left out, never filled in
// with a placeholder or deduced from the name of the block or from the dates of the service fit.
export function provenanceRows(detail: ModelDetail, block: string): [string, string][] {
  const repro = record(detail.reproducibilidad);
  const published = record(blocks(detail)[block]);
  const temporal = Object.keys(published).length
    ? record(valueAt(repro, 'particion_temporal', 'bloques', block))
    : {};
  const pick = (key: string) => textValue(published[key] ?? temporal[key]);
  const cutoff = pick('corte_ajuste');
  const rule = pick('regla_ajuste');
  const bySeason = Object.entries(record(temporal.cortes_por_temporada)).flatMap(
    ([season, value]) => {
      const text = textValue(value);
      return text ? [`${season}: ${shownDate(text)}`] : [];
    },
  );
  const rows: [string, string | null][] = [
    ['Inicio del ajuste de servicio', shownDate(textValue(repro.entrenamiento_inicio))],
    ['Corte del ajuste de servicio', shownDate(textValue(repro.entrenamiento_corte))],
    [
      'Filas del ajuste de servicio',
      finite(repro.filas_entrenamiento) === null ? null : number(finite(repro.filas_entrenamiento)),
    ],
    ['Calibración', textValue(repro.calibracion)],
    ['Intervalo', textValue(repro.intervalo)],
    // A cutoff that is not a date is the rule the version publishes for that block.
    [
      cutoff && !ISO_DATE.test(cutoff)
        ? 'Regla de ajuste del bloque'
        : 'Corte de entrenamiento del bloque',
      shownDate(cutoff),
    ],
    ['Regla de ajuste del bloque', cutoff && !ISO_DATE.test(cutoff) ? null : rule],
    ['Corte de cada temporada', bySeason.length ? bySeason.join(' · ') : null],
    ['Primera semana objetivo del bloque', shownDate(pick('primera_semana_objetivo'))],
    ['Última semana objetivo del bloque', shownDate(pick('ultima_semana_objetivo'))],
  ];
  return rows.flatMap(([label, value]) => (value ? [[label, value] as [string, string]] : []));
}

// The sentence in which the API says that the classifier and the regressor of a horizon share one booster.
export function sharedBoosterNote(detail?: ModelDetail) {
  return textValue(record(detail?.reproducibilidad).nota_importancias);
}

export function metrics(detail: ModelDetail | undefined, id: string) {
  const block = record(blocks(detail)[id]);
  const classifier = record(block.clasificacion);
  const direct = record(classifier.alerta_directa);
  // v0 publishes AUPRC inside alerta_directa; v2 publishes it at clasificacion.
  // An explicit null must stay null, rather than borrowing from another field.
  const auprc = Object.hasOwn(classifier, 'auprc') ? classifier.auprc : direct.auprc;
  return {
    available: Object.keys(block).length > 0,
    recall: probability(direct.recall),
    precision: probability(direct.precision),
    f1: probability(direct.f1),
    auprc: probability(auprc),
    threshold: probability(classifier.umbral_probabilidad),
    mae: finite(valueAt(block, 'regresion', 'conteos', 'mae')),
    rmse: finite(valueAt(block, 'regresion', 'conteos', 'rmse')),
    baselineMae: finite(valueAt(block, 'persistencia', 'conteos', 'mae')),
    baselineRmse: finite(valueAt(block, 'persistencia', 'conteos', 'rmse')),
    n: finite(block.n ?? block.n_prueba ?? direct.n),
    positives: finite(block.positivos ?? direct.positivos),
  };
}

export function baselineRatio(model: number | null, baseline: number | null) {
  return model !== null && baseline !== null && baseline > 0 ? (100 * model) / baseline : null;
}

export function importances(rows: unknown[]) {
  return rows
    .flatMap((row) => {
      const data = record(row);
      const variable = textValue(data.variable);
      const importance = finite(data.importancia);
      const rank = finite(data.rango);
      return variable && importance !== null && rank !== null && Number.isInteger(rank) && rank > 0
        ? [{ variable, importance, rank }]
        : [];
    })
    .sort((a, b) => a.rank - b.rank || a.variable.localeCompare(b.variable));
}
