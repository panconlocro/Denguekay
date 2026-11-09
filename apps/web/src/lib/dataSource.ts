import type { Model } from '../api/types';

export function dataSource(value: string | undefined) {
  return value === 'demo-v2' || value === 'demo-v3' || value === 'fixtures' || value === 'api'
    ? value
    : 'unconfigured';
}

export function demoVersion(source: ReturnType<typeof dataSource>) {
  if (source === 'demo-v2') return 'v2';
  if (source === 'demo-v3') return 'v3';
  return null;
}

// Validate the selected model pair for each horizon of the local demo.
export function verifyDemo(
  models: Pick<Model, 'horizonte' | 'tarea' | 'codigo' | 'algoritmo' | 'seleccion'>[],
  version: 'v2' | 'v3',
) {
  const expected = [2, 3, 4].flatMap((horizon) =>
    ['clasificacion', 'regresion'].map((task) => ({ horizon, task })),
  );
  if (
    models.length !== expected.length ||
    !expected.every(({ horizon, task }) =>
      models.some(
        (model) =>
          model.horizonte === horizon &&
          model.tarea === task &&
          model.codigo.startsWith(
            `${version}-${task === 'clasificacion' ? 'clf' : 'reg'}-h${horizon}-`,
          ) &&
          model.algoritmo === 'xgboost_multisalida_bn' &&
          model.seleccion === 'experimental',
      ),
    )
  )
    throw new Error(
      `La API no corresponde a la demo experimental ${version} esperada. Revisa la conexión.`,
    );
}
