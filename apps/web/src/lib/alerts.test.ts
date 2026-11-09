import { describe, expect, it } from 'vitest';
import type { Alert, District, Prediction } from '../api/types';
import {
  alertContextSearch,
  alertExperimental,
  alertFilters,
  alertProbability,
  selectAlerts,
  sortAlerts,
} from './alerts';
import { dateTime } from './format';

const cut = {
  id_semana: 202552,
  anio: 2025,
  semana: 52,
  fecha_inicio: '2025-12-21',
  fecha_fin: '2025-12-27',
};
const target = {
  id_semana: 202601,
  anio: 2026,
  semana: 1,
  fecha_inicio: '2026-01-04',
  fecha_fin: '2026-01-10',
};
const p: Prediction = {
  disponible: true,
  motivo: null,
  id_prediccion: 1,
  ubigeo: '200101',
  distrito: 'Piura',
  horizonte: 2,
  semana_corte: cut,
  semana_objetivo: target,
  tipo: 'vigente',
  estado: 'disponible',
  probabilidad_brote: 0.8,
  nivel_riesgo: 'muy_alto',
  nivel_riesgo_etiqueta: 'Muy alto',
  casos_estimados: 0.37,
  casos_intervalo_inferior: 0,
  casos_intervalo_superior: 1,
  nivel_intervalo: 0.8,
  motivo_intervalo: null,
  casos_persistencia: 0,
  alerta_modelo: true,
  experimental: true,
  id_version_clasificador: 1,
  id_version_regresor: 2,
  id_ejecucion: 1,
  fecha_generacion: '2026-11-04T23:00:00Z',
};
function alert(id: number, overrides: Partial<Alert> = {}): Alert {
  return {
    id_alerta: id,
    ubigeo: '200101',
    distrito: 'Piura',
    horizonte: 2,
    nivel: 'muy_alto',
    nivel_etiqueta: 'Muy alto',
    estado: 'activa',
    cambio: 'nueva',
    fecha_generacion: p.fecha_generacion,
    fecha_retiro: null,
    motivo: null,
    experimental: true,
    prediccion: p,
    ...overrides,
  };
}
const districts: District[] = [
  {
    ubigeo: '200101',
    nombre: 'Piura',
    ubigeo_provincia: '2001',
    provincia: 'Piura',
    latitud: -5.2,
    longitud: -80.6,
    poblacion_censo_2017: null,
    activo: true,
  },
];

describe('alert history integrity', () => {
  it('orders by stored level then probability and allows independent probability or date ordering', () => {
    const rows = [
      alert(1, { nivel: 'alto', prediccion: { ...p, probabilidad_brote: 0.99 } }),
      alert(2),
      alert(3, {
        fecha_generacion: '2026-11-05T23:00:00Z',
        prediccion: { ...p, probabilidad_brote: 0.7 },
      }),
    ];
    expect(sortAlerts(rows, 'riesgo').map((a) => a.id_alerta)).toEqual([2, 3, 1]);
    expect(sortAlerts(rows, 'probabilidad').map((a) => a.id_alerta)).toEqual([1, 2, 3]);
    expect(sortAlerts(rows, 'fecha').map((a) => a.id_alerta)).toEqual([3, 2, 1]);
    expect(rows.map((a) => a.id_alerta)).toEqual([1, 2, 3]);
  });
  it('breaks ties deterministically and places unknown probabilities after a genuine zero', () => {
    expect(sortAlerts([alert(1), alert(2)], 'riesgo').map((a) => a.id_alerta)).toEqual([2, 1]);
    const zero = alert(1, { prediccion: { ...p, probabilidad_brote: 0 } });
    const unavailable = alert(2, {
      prediccion: { ...p, disponible: false, probabilidad_brote: 0.99 },
    });
    expect(alertProbability(unavailable)).toBeNull();
    expect(sortAlerts([unavailable, zero], 'probabilidad')[0].id_alerta).toBe(1);
  });
  it('filters state, district, horizon and target without substituting the latest regional week', () => {
    const rows = [
      alert(1),
      alert(2, { estado: 'retirada' }),
      alert(3, { horizonte: 4 }),
      alert(4, { prediccion: { ...p, ubigeo: '200104' } }),
    ];
    expect(
      selectAlerts(rows, 'activa', 2, districts, '2001', '200101', 'muy_alto', '202601').map(
        (a) => a.id_alerta,
      ),
    ).toEqual([1]);
    expect(selectAlerts(rows, 'activa', 2, districts, '2002', '', '', '')).toHaveLength(0);
    expect(selectAlerts(rows, 'activa', 2, districts, '', '', '', '202602')).toHaveLength(0);
  });
  it('retains the stored retirement level independently of an updated linked prediction', () => {
    const retired = alert(1, {
      estado: 'retirada',
      prediccion: { ...p, probabilidad_brote: 0.2, nivel_riesgo: 'bajo' },
    });
    expect(selectAlerts([retired], 'retirada', 2, districts, '', '', 'muy_alto', '')).toHaveLength(
      1,
    );
    expect(alertProbability(retired)).toBe(0.2);
    expect(alertExperimental({ ...retired, experimental: false })).toBe(true);
  });
  it('canonicalizes a deep link to the record own horizon, state and district', () => {
    const url = new URL(
      `http://localhost/alertas/1${alertContextSearch(alert(1, { estado: 'retirada' }), '?horizonte=4&distrito=999999&provincia=9999', districts)}`,
    );
    expect([...url.searchParams.entries()]).toEqual([
      ['horizonte', '2'],
      ['distrito', '200101'],
      ['provincia', '2001'],
      ['aviso_estado', 'retirada'],
    ]);
  });
});

describe('alert filters and dates', () => {
  it('validates URL filters before presenting totals', () => {
    expect(alertFilters(new URLSearchParams()).error).toBe(false);
    expect(
      alertFilters(
        new URLSearchParams(
          'aviso_estado=retirada&aviso_nivel=alto&aviso_orden=fecha&aviso_semana=202601&aviso_pagina=2',
        ),
      ).error,
    ).toBe(false);
    for (const query of [
      'aviso_estado=otra',
      'aviso_nivel=bajo',
      'aviso_orden=otro',
      'aviso_semana=202654',
      'aviso_pagina=0',
      'aviso_pagina=9007199254740992',
    ])
      expect(alertFilters(new URLSearchParams(query)).error).toBe(true);
  });
  it('shows generation and retirement times in Lima while retaining absent dates', () => {
    expect(dateTime('2026-01-02T00:00:00Z')).toBe('01/01/2026 · 19:00 (Lima)');
    expect(dateTime(null)).toBe('Sin fecha publicada');
  });
});
