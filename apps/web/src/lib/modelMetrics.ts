import type { Model, ModelDetail } from '../api/types';

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
  return id.replace(/^temporada_/, 'Temporada ').replace(/^calendario_/, 'Calendario ');
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
