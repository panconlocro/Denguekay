import { afterEach, describe, expect, it, vi } from 'vitest';
import { allPages, ApiError, get } from './client';
import type { Page } from './types';

afterEach(() => vi.unstubAllGlobals());
describe('read-only API client', () => {
  it('loads every page before sorting or filtering data', async () => {
    const read = vi.fn(async (page: number): Promise<Page<string>> => ({
      disponible: true,
      fecha_actualizacion: null,
      fecha_corte_datos: null,
      total: 3,
      pagina: page,
      tamano_pagina: 2,
      elementos: page === 1 ? ['a', 'b'] : ['c'],
    }));
    expect((await allPages(read)).elementos).toEqual(['a', 'b', 'c']);
    expect(read).toHaveBeenCalledWith(2);
  });
  it('fails the whole result when a later page fails', async () => {
    await expect(
      allPages(async (page) => {
        if (page > 1) throw new Error('second page unavailable');
        return {
          disponible: true,
          fecha_actualizacion: null,
          fecha_corte_datos: null,
          total: 3,
          pagina: 1,
          tamano_pagina: 2,
          elementos: ['a', 'b'],
        };
      }),
    ).rejects.toThrow('second page unavailable');
  });
  it('preserves textual ubigeos and does not send write credentials', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    await get('/api/v1/distritos/{ubigeo}', {}, undefined, { ubigeo: '010101' });
    expect(fetch.mock.calls[0][0]).toBe('/api/v1/distritos/010101');
    expect(fetch.mock.calls[0][1].headers).toEqual({ Accept: 'application/json' });
  });
  it('preserves structured service errors and rejects incompatible contracts', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ codigo: 'bd_no_disponible', mensaje: 'Base de datos no disponible' }),
            { status: 503 },
          ),
        ),
    );
    await expect(get('/api/v1/configuracion')).rejects.toMatchObject({
      status: 503,
      code: 'bd_no_disponible',
    });
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('{}', { headers: { 'X-Version-Contrato': '2.0.0' } })),
    );
    await expect(get('/api/v1/configuracion')).rejects.toBeInstanceOf(ApiError);
  });
});
