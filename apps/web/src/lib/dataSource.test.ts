import { describe, expect, it } from 'vitest';
import { dataSource, demoVersion, verifyDemo } from './dataSource';

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
  it('requires explicit provenance instead of assuming a local demo version', () => {
    expect(dataSource(undefined)).toBe('unconfigured');
    expect(dataSource('v2')).toBe('unconfigured');
    expect(dataSource('fixtures')).toBe('fixtures');
    expect(dataSource('demo-v2')).toBe('demo-v2');
    expect(dataSource('api')).toBe('api');
    expect(demoVersion(dataSource('demo-v3'))).toBe('v3');
    expect(demoVersion(dataSource('demo-v2'))).toBe('v2');
    expect(demoVersion(dataSource('api'))).toBeNull();
  });
  it.each(['v2', 'v3'] as const)('accepts the six selected %s versions in any order', (version) => {
    const versions = models.map((model) => ({
      ...model,
      codigo: model.codigo.replace(/^v2/, version),
    }));
    expect(() => verifyDemo(versions.reverse(), version)).not.toThrow();
  });
  it('rejects a v2 database in the v3 demo', () => {
    expect(() => verifyDemo(models, 'v3')).toThrow('demo experimental v3 esperada');
  });
  it('rejects v0 fixtures, partial selections and duplicate task/horizon pairs', () => {
    expect(() =>
      verifyDemo(
        models.map((m) => ({ ...m, codigo: 'v0-clf-h2-1' })),
        'v2',
      ),
    ).toThrow();
    expect(() => verifyDemo(models.slice(0, 4), 'v2')).toThrow();
    expect(() => verifyDemo([models[0], ...models.slice(0, 5)], 'v2')).toThrow();
  });
});
