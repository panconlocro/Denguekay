import { describe, expect, it } from 'vitest';
import { dataSource, verifyDemoV2 } from './dataSource';

const models = [2, 3, 4].flatMap((horizon) =>
  (['clasificacion', 'regresion'] as const).map((task) => ({
    horizonte: horizon,
    tarea: task,
    codigo: `v2-${task === 'clasificacion' ? 'clf' : 'reg'}-h${horizon}-1`,
    algoritmo: 'xgboost_multisalida_bn',
    seleccion: 'experimental' as const,
  })),
);

describe('local demo identity', () => {
  it('requires explicit provenance instead of assuming local data is v2', () => {
    expect(dataSource(undefined)).toBe('unconfigured');
    expect(dataSource('v2')).toBe('unconfigured');
    expect(dataSource('fixtures')).toBe('fixtures');
    expect(dataSource('demo-v2')).toBe('demo-v2');
    expect(dataSource('api')).toBe('api');
  });
  it('accepts the six selected v2 versions, regardless of their order', () => {
    expect(() => verifyDemoV2([...models].reverse())).not.toThrow();
  });
  it('rejects v0 fixtures, partial selections and duplicate task/horizon pairs', () => {
    expect(() => verifyDemoV2(models.map((m) => ({ ...m, codigo: 'v0-clf-h2-1' })))).toThrow();
    expect(() => verifyDemoV2(models.slice(0, 4))).toThrow();
    expect(() => verifyDemoV2([models[0], ...models.slice(0, 5)])).toThrow();
  });
});
