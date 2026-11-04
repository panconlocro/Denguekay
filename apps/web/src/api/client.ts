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
  const response = await fetch(`${base}${resolved}${query.size ? `?${query}` : ''}`, {
    signal,
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
  return response.json();
}

// Filtering or sorting a catalogue requires all pages, never just the visible first page.
export async function allPages<T>(read: (page: number) => Promise<Page<T>>): Promise<Page<T>> {
  const first = await read(1);
  const pages = Math.ceil(first.total / first.tamano_pagina);
  const rest = await Promise.all(
    Array.from({ length: Math.max(0, pages - 1) }, (_, i) => read(i + 2)),
  );
  return { ...first, elementos: [first, ...rest].flatMap((p) => p.elementos) };
}
