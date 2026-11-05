import type { Model } from '../api/types';

export function dataSource(value: string | undefined) {
  return value === 'demo-v2' || value === 'fixtures' || value === 'api' ? value : 'unconfigured';
}

// This is the identity expected by the explicit local demo recipe, not a general API restriction.
export function verifyDemoV2(
  models: Pick<Model, 'horizonte' | 'tarea' | 'codigo' | 'algoritmo' | 'seleccion'>[],
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
          model.codigo.startsWith(`v2-${task === 'clasificacion' ? 'clf' : 'reg'}-h${horizon}-`) &&
          model.algoritmo === 'xgboost_multisalida_bn' &&
          model.seleccion === 'experimental',
      ),
    )
  )
    throw new Error(
      'La API no corresponde a la demo experimental v2 esperada. Revisa la conexión.',
    );
}
