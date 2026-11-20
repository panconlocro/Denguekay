import { describe, expect, it } from 'vitest';
import { horizonStatus, number, percent, riskRange } from './format';

describe('presentation invariants', () => {
  it('keeps risk boundaries unambiguous', () => {
    expect(riskRange(0, 0.25)).toBe('< 25 %');
    expect(riskRange(0.25, 0.5)).toBe('25 % – < 50 %');
    expect(riskRange(0.75, 1)).toBe('≥ 75 %');
  });
  it('keeps a missing value separate from a notified zero', () => {
    expect(number(null)).toBe('No disponible');
    expect(number(0)).toBe('0');
    expect(number(1284)).toBe('1 284');
    expect(number(0.82, 2)).toBe('0,82');
    expect(percent(null)).toBe('Sin datos');
  });
  it('never calls an experimental model operational', () => {
    const h = { horizonte: 4, disponible: true, experimental: true, semana_corte_vigente: null };
    expect(horizonStatus(h)).toBe('Experimental');
    expect(horizonStatus({ ...h, experimental: false })).toBe('Validado');
    expect(horizonStatus({ ...h, disponible: false })).toBe('No disponible');
  });
});
