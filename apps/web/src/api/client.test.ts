import { afterEach, describe, expect, it, vi } from 'vitest';
import { allPages, ApiError, get } from './client';
import type { Page } from './types';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

function dataPage<T>(page: number, elements: T[], overrides: Partial<Page<T>> = {}): Page<T> {
  return {
    disponible: true,
    fecha_corte_datos: '2025-12-27',
    fecha_actualizacion: '2026-11-05T00:00:00Z',
    total: 3,
    pagina: page,
    tamano_pagina: 2,
    elementos: elements,
    ...overrides,
  };
}

function untilAborted(signal: AbortSignal): Promise<never> {
  return new Promise((_, reject) => {
    if (signal.aborted) reject(signal.reason);
    else signal.addEventListener('abort', () => reject(signal.reason), { once: true });
  });
}

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

describe('complete and consistent pagination', () => {
  it.each([true, false])('preserves an empty first page with disponible=%s', async (available) => {
    const first = dataPage(1, [], {
      disponible: available,
      total: 0,
      motivo: available ? null : 'Sin publicación disponible',
    });
    const read = vi.fn().mockResolvedValue(first);
    expect(await allPages(read)).toBe(first);
    expect(read).toHaveBeenCalledExactlyOnceWith(1);
  });

  it.each([
    ['unavailable HTTP 200', { disponible: false, elementos: [] }],
    ['changed total', { total: 4 }],
    ['changed cutoff', { fecha_corte_datos: '2026-01-03' }],
    ['changed update', { fecha_actualizacion: '2026-11-05T01:00:00Z' }],
    ['missing update', { fecha_actualizacion: undefined }],
    ['changed page size', { tamano_pagina: 3 }],
    ['repeated page number', { pagina: 1 }],
    ['missing final row', { elementos: [] }],
    ['extra final row', { elementos: ['c', 'd'] }],
  ] satisfies [string, Partial<Page<string>>][])(
    'rejects a second page with %s',
    async (_, change) => {
      const result = allPages(async (page) =>
        page === 1 ? dataPage(1, ['a', 'b']) : dataPage(2, ['c'], change),
      );
      await expect(result).rejects.toBeInstanceOf(ApiError);
      await expect(result).rejects.toMatchObject({ status: 502, code: 'paginacion_inconsistente' });
    },
  );

  it.each([
    ['negative total', { total: -1 }],
    ['fractional total', { total: 1.5 }],
    ['unsafe total', { total: Number.MAX_SAFE_INTEGER + 1 }],
    ['zero page size', { tamano_pagina: 0 }],
    ['fractional page size', { tamano_pagina: 1.5 }],
    ['wrong initial page', { pagina: 2 }],
    ['missing initial rows', { elementos: ['a'] }],
    ['unavailable with rows', { disponible: false }],
    ['unavailable but nonzero total', { disponible: false, elementos: [] }],
    ['empty total with rows', { total: 0 }],
  ] satisfies [string, Partial<Page<string>>][])(
    'rejects %s before reading more pages',
    async (_, change) => {
      const read = vi.fn().mockResolvedValue(dataPage(1, ['a', 'b'], change));
      await expect(allPages(read)).rejects.toMatchObject({ code: 'paginacion_inconsistente' });
      expect(read).toHaveBeenCalledExactlyOnceWith(1);
    },
  );

  it('rejects missing rows in an intermediate page', async () => {
    await expect(
      allPages(async (page) =>
        dataPage(page, page === 1 ? ['a', 'b'] : [String(page)], { total: 5 }),
      ),
    ).rejects.toMatchObject({ code: 'paginacion_inconsistente' });
  });

  it('rejects duplicate rows across pages instead of silently deduplicating', async () => {
    await expect(
      allPages(async (page) => dataPage(page, page === 1 ? ['a', 'b'] : ['a'])),
    ).rejects.toMatchObject({ code: 'paginacion_inconsistente' });
  });

  it('rejects duplicates within the first page', async () => {
    const read = vi.fn().mockResolvedValue(dataPage(1, ['a', 'a']));
    await expect(allPages(read)).rejects.toMatchObject({ code: 'paginacion_inconsistente' });
    expect(read).toHaveBeenCalledTimes(1);
  });

  it.each(['id_alerta', 'id_prediccion', 'ubigeo'])(
    'rejects repeated resource key %s with changed fields',
    async (key) => {
      await expect(
        allPages(async (page) =>
          dataPage(page, [{ [key]: '200101', label: `page ${page}` }], {
            total: 2,
            tamano_pagina: 1,
          }),
        ),
      ).rejects.toMatchObject({ code: 'paginacion_inconsistente' });
    },
  );

  it('compares fallback objects independently of property order', async () => {
    await expect(
      allPages(async (page) =>
        dataPage(page, page === 1 ? [{ a: 1, b: 2 }] : [{ b: 2, a: 1 }], {
          total: 2,
          tamano_pagina: 1,
        }),
      ),
    ).rejects.toMatchObject({ code: 'paginacion_inconsistente' });
  });

  it('uses district and week together as the observation key', async () => {
    const read = async (page: number) =>
      dataPage(page, [{ ubigeo: '200101', semana: { id_semana: 202500 + page } }], {
        total: 2,
        tamano_pagina: 1,
      });
    expect((await allPages(read)).elementos).toHaveLength(2);
    await expect(
      allPages(async (page) => {
        const result = await read(page);
        return {
          ...result,
          elementos: [{ ubigeo: '200101', semana: { id_semana: 202501 }, casos_dengue: page }],
        };
      }),
    ).rejects.toMatchObject({ code: 'paginacion_inconsistente' });
  });

  it('loads every page in order with at most four concurrent reads', async () => {
    let active = 0;
    let maximum = 0;
    const release = new Map<number, () => void>();
    const read = vi.fn(async (page: number) => {
      if (page > 1) {
        active++;
        maximum = Math.max(maximum, active);
        await new Promise<void>((resolve) => release.set(page, resolve));
        active--;
      }
      return dataPage(page, [page], { total: 13, tamano_pagina: 1 });
    });
    const result = allPages(read);
    await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(5));
    expect(maximum).toBe(4);
    // Complete the first batch backwards to check that completion order is not row order.
    for (const page of [5, 4, 3, 2, 6, 7, 8, 9, 10, 11, 12, 13]) {
      await vi.waitFor(() => expect(release.has(page)).toBe(true));
      release.get(page)!();
    }
    expect((await result).elementos).toEqual(Array.from({ length: 13 }, (_, i) => i + 1));
    expect(read).toHaveBeenCalledTimes(13);
    expect(maximum).toBe(4);
    expect(active).toBe(0);
  });

  it('stops scheduling queued pages after a read fails', async () => {
    const read = vi.fn(async (page: number) => {
      if (page === 2) throw new Error('page failed');
      return dataPage(page, [page], { total: 20, tamano_pagina: 1 });
    });
    await expect(allPages(read)).rejects.toThrow('page failed');
    expect(read.mock.calls.map(([page]) => page)).toEqual([1, 2, 3, 4, 5]);
  });
});

describe('request deadline and cancellation', () => {
  it('aborts a stalled fetch at 20 seconds with a retryable ApiError', async () => {
    vi.useFakeTimers();
    const caller = new AbortController();
    const add = vi.spyOn(caller.signal, 'addEventListener');
    const remove = vi.spyOn(caller.signal, 'removeEventListener');
    let requestSignal: AbortSignal;
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init: RequestInit) => {
        requestSignal = init.signal as AbortSignal;
        return untilAborted(requestSignal);
      }),
    );
    const result = get('/api/v1/configuracion', {}, caller.signal);
    const rejection = expect(result).rejects.toMatchObject({
      status: 504,
      code: 'tiempo_espera_agotado',
      message: expect.stringMatching(/reintenta/i),
    });
    await vi.advanceTimersByTimeAsync(19_999);
    expect(requestSignal!.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    await rejection;
    expect(requestSignal!.aborted).toBe(true);
    expect(caller.signal.aborted).toBe(false);
    expect(remove).toHaveBeenCalledWith('abort', add.mock.calls[0][1]);
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each(['timeout', 'caller'])(
    'keeps %s cancellation active while consuming JSON',
    async (source) => {
      vi.useFakeTimers();
      const caller = new AbortController();
      const reason = new DOMException('Navigation cancelled', 'AbortError');
      const reading = vi.fn();
      vi.stubGlobal(
        'fetch',
        vi.fn(async (_url: string, init: RequestInit) => ({
          ok: true,
          headers: new Headers(),
          json: () => {
            reading();
            return untilAborted(init.signal as AbortSignal);
          },
        })),
      );
      const result = get('/api/v1/configuracion', {}, caller.signal);
      const rejection =
        source === 'timeout'
          ? expect(result).rejects.toMatchObject({ code: 'tiempo_espera_agotado' })
          : expect(result).rejects.toBe(reason);
      await vi.advanceTimersByTimeAsync(0);
      expect(reading).toHaveBeenCalledTimes(1);
      if (source === 'timeout') await vi.advanceTimersByTimeAsync(20_000);
      else caller.abort(reason);
      await rejection;
      expect(vi.getTimerCount()).toBe(0);
    },
  );

  it('forwards caller cancellation during fetch without relabeling it as a timeout', async () => {
    vi.useFakeTimers();
    const caller = new AbortController();
    const remove = vi.spyOn(caller.signal, 'removeEventListener');
    const reason = new DOMException('Navigation cancelled', 'AbortError');
    let requestSignal: AbortSignal;
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init: RequestInit) => {
        requestSignal = init.signal as AbortSignal;
        return untilAborted(requestSignal);
      }),
    );
    const result = get('/api/v1/configuracion', {}, caller.signal);
    const rejection = expect(result).rejects.toBe(reason);
    await vi.advanceTimersByTimeAsync(1_000);
    caller.abort(reason);
    await rejection;
    expect(requestSignal!.reason).toBe(reason);
    expect(remove).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('does not fetch when the caller signal is already aborted', async () => {
    vi.useFakeTimers();
    const caller = new AbortController();
    caller.abort();
    const add = vi.spyOn(caller.signal, 'addEventListener');
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    await expect(get('/api/v1/configuracion', {}, caller.signal)).rejects.toBe(
      caller.signal.reason,
    );
    expect(fetch).not.toHaveBeenCalled();
    expect(add).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each(['success', 'http error', 'network error', 'invalid JSON', 'incompatible contract'])(
    'cleans up timers and caller listeners after %s',
    async (outcome) => {
      vi.useFakeTimers();
      const caller = new AbortController();
      const add = vi.spyOn(caller.signal, 'addEventListener');
      const remove = vi.spyOn(caller.signal, 'removeEventListener');
      const response =
        outcome === 'http error'
          ? new Response('{}', { status: 503 })
          : outcome === 'invalid JSON'
            ? new Response('invalid JSON')
            : new Response('{}', {
                headers:
                  outcome === 'incompatible contract' ? { 'X-Version-Contrato': '2.0.0' } : {},
              });
      const fetch = vi.fn();
      if (outcome === 'network error')
        fetch.mockRejectedValue(new TypeError('Network unavailable'));
      else fetch.mockResolvedValue(response);
      vi.stubGlobal('fetch', fetch);
      const result = get('/api/v1/configuracion', {}, caller.signal);
      if (outcome === 'success') await expect(result).resolves.toEqual({});
      else await expect(result).rejects.toBeInstanceOf(Error);
      expect(remove).toHaveBeenCalledWith('abort', add.mock.calls[0][1]);
      expect(vi.getTimerCount()).toBe(0);
      const requestSignal = fetch.mock.calls[0][1].signal as AbortSignal;
      caller.abort();
      expect(requestSignal.aborted).toBe(false);
      await vi.advanceTimersByTimeAsync(20_000);
      expect(requestSignal.aborted).toBe(false);
    },
  );
});
