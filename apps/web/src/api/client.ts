import type { paths } from './schema';
import type { Page } from './types';

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

type ReadPath = { [K in keyof paths]: paths[K] extends { get: object } ? K : never }[keyof paths];
type ReadResult<P extends ReadPath> = paths[P] extends {
  get: { responses: { 200: { content: { 'application/json': infer T } } } };
}
  ? T
  : never;
type Params = Record<string, string | number | undefined>;
const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');

export async function get<P extends ReadPath>(
  path: P,
  params: Params = {},
  signal?: AbortSignal,
  replacements: Record<string, string | number> = {},
): Promise<ReadResult<P>> {
  const resolved = path
    .replace('/api/v1', '')
    .replace(/\{([^}]+)\}/g, (_, key: string) => encodeURIComponent(String(replacements[key])));
  const query = new URLSearchParams(
    Object.entries(params)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => [k, String(v)]),
  );
  const controller = new AbortController();
  const cancel = () => controller.abort(signal?.reason);
  const timeoutError = new ApiError(
    504,
    'tiempo_espera_agotado',
    'El servicio tardó más de 20 segundos en responder. Reintenta la consulta.',
  );
  let timedOut = false;
  const timer = setTimeout(() => {
    if (controller.signal.aborted) return;
    timedOut = true;
    controller.abort(timeoutError);
  }, 20_000);
  if (signal?.aborted) cancel();
  else signal?.addEventListener('abort', cancel, { once: true });
  try {
    if (controller.signal.aborted) throw controller.signal.reason;
    const response = await fetch(`${base}${resolved}${query.size ? `?${query}` : ''}`, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    if (!response.ok) {
      const error = await response.json().catch(() => null);
      throw new ApiError(
        response.status,
        error?.codigo || 'servicio_no_disponible',
        error?.mensaje || 'No se pudo consultar el servicio. Inténtalo nuevamente.',
      );
    }
    const version = response.headers.get('X-Version-Contrato');
    if (version && version.split('.')[0] !== '1')
      throw new ApiError(
        502,
        'contrato_incompatible',
        'La versión de la API no es compatible con esta aplicación.',
      );
    // Keep the deadline and cancellation active while reading the response body.
    return await response.json();
  } catch (error) {
    if (timedOut) throw timeoutError;
    if (controller.signal.aborted) throw controller.signal.reason;
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
  }
}

function paginationError() {
  return new ApiError(
    502,
    'paginacion_inconsistente',
    'No se pudo obtener un listado completo y coherente. Reintenta la consulta.',
  );
}

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === 'object')
    return Object.fromEntries(
      Object.entries(value)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, item]) => [key, canonical(item)]),
    );
  return value;
}

function rowIdentity(value: unknown): string {
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    const row = value as Record<string, unknown>;
    // Use the resource keys of the paginated endpoints, even if other fields changed.
    for (const key of ['id_alerta', 'id_prediccion'])
      if (row[key] != null) return JSON.stringify([key, row[key]]);
    if (typeof row.ubigeo === 'string') {
      const week = row.semana as { id_semana?: unknown } | null | undefined;
      return JSON.stringify(['ubigeo', row.ubigeo, week?.id_semana ?? null]);
    }
  }
  return JSON.stringify(canonical(value)) ?? String(value);
}

// Filtering or sorting a catalogue requires all pages, never just the visible first page.
export async function allPages<T>(read: (page: number) => Promise<Page<T>>): Promise<Page<T>> {
  const first = await read(1);
  const seen = new Set<string>();
  const validate = (result: Page<T>, page: number) => {
    if (
      !result ||
      typeof result.disponible !== 'boolean' ||
      !Number.isSafeInteger(result.total) ||
      result.total < 0 ||
      !Number.isSafeInteger(result.tamano_pagina) ||
      result.tamano_pagina <= 0 ||
      result.pagina !== page ||
      !Array.isArray(result.elementos) ||
      ![result.fecha_corte_datos, result.fecha_actualizacion].every(
        (date) => date === null || typeof date === 'string',
      ) ||
      (!result.disponible && !(page === 1 && result.total === 0)) ||
      result.disponible !== first.disponible ||
      result.total !== first.total ||
      result.tamano_pagina !== first.tamano_pagina ||
      result.fecha_corte_datos !== first.fecha_corte_datos ||
      result.fecha_actualizacion !== first.fecha_actualizacion ||
      result.elementos.length !==
        Math.min(result.tamano_pagina, result.total - (page - 1) * result.tamano_pagina)
    )
      throw paginationError();
    for (const row of result.elementos) {
      const identity = rowIdentity(row);
      if (seen.has(identity)) throw paginationError();
      seen.add(identity);
    }
  };
  validate(first, 1);
  if (first.total === 0) return first;
  const pages = Math.ceil(first.total / first.tamano_pagina);
  const rows = [first.elementos];
  let nextPage = 2;
  let failed = false;
  const worker = async () => {
    while (!failed && nextPage <= pages) {
      const page = nextPage++;
      try {
        const result = await read(page);
        if (failed) return;
        validate(result, page);
        rows[page - 1] = result.elementos;
      } catch (error) {
        failed = true;
        throw error;
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(4, pages - 1) }, () => worker()));
  return { ...first, elementos: rows.flat() };
}
