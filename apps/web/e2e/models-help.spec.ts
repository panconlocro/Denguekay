import { test, expect, type Page } from '@playwright/test';
import type { Model, ModelDetail } from '../src/api/types';
import { metrics } from '../src/lib/modelMetrics';
import { number } from '../src/lib/format';
import { readFileSync } from 'node:fs';

const help = JSON.parse(
  readFileSync(new URL('../src/content/help.json', import.meta.url), 'utf8'),
) as { topics: { title: string; liveLegend?: boolean }[] };

function card(page: Page, title: string) {
  return page
    .locator('.card')
    .filter({ has: page.getByRole('heading', { name: title, exact: true }) });
}
async function versions(page: Page, horizon: number) {
  return (await (await page.request.get(`/api/v1/modelos/activo?horizonte=${horizon}`)).json())
    .elementos as Model[];
}
async function detail(page: Page, model: Model) {
  return (await (
    await page.request.get(`/api/v1/modelos/${model.id_version}`)
  ).json()) as ModelDetail;
}

test('published periods, task versions and importances remain traceable across horizons', async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const config = await (await page.request.get('/api/v1/configuracion')).json();
  await page.goto('/modelo?horizonte=2');
  await expect(page.getByLabel('Bloque de evaluación')).toHaveValue('calendario_2025');
  await page.getByLabel('Bloque de evaluación').selectOption('temporada_2024');
  for (const horizon of config.horizontes_disponibles as number[]) {
    const selected = await versions(page, horizon);
    const clf = selected.find((m) => m.tarea === 'clasificacion')!;
    const reg = selected.find((m) => m.tarea === 'regresion')!;
    const c = metrics(await detail(page, clf), 'temporada_2024');
    const r = metrics(await detail(page, reg), 'temporada_2024');
    await page.getByRole('button', { name: new RegExp(`^${horizon} semanas`) }).click();
    await expect(page.getByLabel('Bloque de evaluación')).toHaveValue('temporada_2024');
    await expect(card(page, 'Clasificación de brotes').locator('.metric-value')).toHaveText(
      [c.recall, c.precision, c.f1, c.auprc].map((v) => number(v, 3)),
    );
    await expect(card(page, 'Clasificación de brotes')).toContainText(clf.codigo);
    await expect(
      card(page, 'Magnitud frente a persistencia').locator('tbody tr').first(),
    ).toContainText(number(r.mae, 3));
    const importances = await (
      await page.request.get(`/api/v1/modelos/${reg.id_version}/variables`)
    ).json();
    await expect(page.locator('.importance-data')).toContainText(reg.codigo);
    await expect(page.locator('.importance-data')).toContainText(importances.nota);
    await expect(page.locator('.importance-list li').first()).toContainText(
      importances.elementos[0].variable,
    );
    await expect(page.locator('.importance-list li').first()).toContainText(
      number(importances.elementos[0].importancia, 5),
    );
    await expect(page.locator('.horizon-performance tbody tr')).toHaveCount(
      config.horizontes.length,
    );
    const row = page
      .locator('.horizon-performance tbody tr')
      .filter({ hasText: `${horizon} semanas` });
    await expect(row).toContainText(clf.codigo);
    await expect(row).toContainText(number(c.recall, 3));
    await expect(card(page, 'Versiones en uso')).toContainText('Selección de servicio');
    await expect(card(page, 'Protocolo temporal y reproducibilidad')).toContainText('ajuste');
  }
  await page.getByLabel('Versión para importancias').selectOption('clasificacion');
  await expect(page.locator('.importance-data')).toContainText('clf');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.evaluate(() => {
    (document.activeElement as HTMLElement)?.blur();
    window.scrollTo(0, 0);
  });
  if (process.env.WEB_SCREENSHOT_DIR)
    await page.screenshot({
      path: `${process.env.WEB_SCREENSHOT_DIR}/${testInfo.project.name}-models-${process.env.WEB_TEST_SOURCE || 'fixtures'}.png`,
      fullPage: true,
    });
  expect(errors).toEqual([]);
});

test('zero, null, absent blocks and raw importance methods are not replaced', async ({ page }) => {
  const selected = await versions(page, 2);
  for (const model of selected)
    await page.route(`**/api/v1/modelos/${model.id_version}`, async (route) => {
      const response = await route.fetch();
      const data = await response.json();
      data.metricas = {
        bloques: {
          calendario_2025:
            model.tarea === 'clasificacion'
              ? {
                  n: 7,
                  positivos: 2,
                  clasificacion: {
                    auprc: null,
                    alerta_directa: { recall: 0, precision: null, f1: '0.8', auprc: 0.9 },
                  },
                }
              : {
                  n: 7,
                  regresion: { conteos: { mae: 0, rmse: 2 } },
                  persistencia: { conteos: { mae: 0, rmse: 4 } },
                },
        },
      };
      await route.fulfill({ response, json: data });
    });
  const reg = selected.find((m) => m.tarea === 'regresion')!;
  await page.route(`**/api/v1/modelos/${reg.id_version}/variables`, async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.nota = 'Importancia gain del booster; no implica causalidad';
    data.elementos = [{ variable: 'variable_control', importancia: 12.8, rango: 1 }];
    await route.fulfill({ response, json: data });
  });
  await page.goto('/modelo?horizonte=2');
  await expect(card(page, 'Clasificación de brotes').locator('.metric-value')).toHaveText([
    '0',
    'No disponible',
    'No disponible',
    'No disponible',
  ]);
  await expect(
    card(page, 'Magnitud frente a persistencia').locator('tbody tr').first().locator('td'),
  ).toHaveText(['0', '0', 'No disponible']);
  await expect(
    card(page, 'Magnitud frente a persistencia').locator('tbody tr').nth(1).locator('td'),
  ).toHaveText(['2', '4', '50 %']);
  await expect(page.locator('.importance-list')).toContainText('12,8');
  await expect(page.locator('.importance-data')).toContainText('gain');
  await page.goto('/modelo?horizonte=2&modelo_bloque=bloque_inexistente');
  await expect(
    page.getByRole('heading', { name: 'Bloque no publicado', exact: true }),
  ).toBeVisible();
  await expect(page.locator('.classification-metrics')).toHaveCount(0);
  await page.getByRole('button', { name: 'Usar último bloque publicado' }).click();
  await expect(page.locator('.classification-metrics')).toBeVisible();
});

test('detail and importance failures clear only their own results and recover', async ({
  page,
}) => {
  const selected = await versions(page, 4);
  const reg = selected.find((m) => m.tarea === 'regresion')!;
  const fail = (route: import('@playwright/test').Route) =>
    route.fulfill({
      status: 503,
      json: { codigo: 'bd_no_disponible', mensaje: 'Consulta temporalmente no disponible' },
    });
  await page.goto('/modelo?horizonte=2');
  await expect(page.locator('.baseline-table')).toBeVisible();
  await page.route(`**/api/v1/modelos/${reg.id_version}`, fail);
  await page.getByRole('button', { name: /^4 semanas/ }).click();
  await expect(card(page, 'Magnitud frente a persistencia').getByRole('alert')).toBeVisible();
  await expect(page.locator('.baseline-table')).toHaveCount(0);
  await expect(page.locator('.classification-metrics')).toBeVisible();
  await expect(page.locator('.importance-data')).toContainText(reg.codigo);
  await page.unroute(`**/api/v1/modelos/${reg.id_version}`);
  await card(page, 'Magnitud frente a persistencia')
    .getByRole('button', { name: 'Reintentar', exact: true })
    .click();
  await expect(page.locator('.baseline-table')).toBeVisible();
  await page.route(`**/api/v1/modelos/${reg.id_version}/variables`, fail);
  await page.getByLabel('Versión para importancias').selectOption('clasificacion');
  await expect(page.locator('.importance-data')).toContainText('clf');
  await page.getByLabel('Versión para importancias').selectOption('regresion');
  await expect(card(page, 'Importancia de variables').getByRole('alert')).toBeVisible();
  await expect(page.locator('.importance-list')).toHaveCount(0);
  await expect(page.locator('.baseline-table')).toBeVisible();
  await page.unroute(`**/api/v1/modelos/${reg.id_version}/variables`);
  await card(page, 'Importancia de variables')
    .getByRole('button', { name: 'Reintentar', exact: true })
    .click();
  await expect(page.locator('.importance-data')).toContainText(reg.codigo);
  await expect(page.locator('.importance-list')).toBeVisible();
});

test('help search, live legend, navigation and actual PDF download', async ({ page }, testInfo) => {
  const config = await (await page.request.get('/api/v1/configuracion')).json();
  await page.goto('/ayuda?horizonte=2');
  await expect(
    page.getByRole('heading', { name: 'Ayuda y manual', exact: true, level: 1 }),
  ).toBeVisible();
  const search = page.getByRole('searchbox', { name: 'Buscar en la ayuda' });
  await search.fill('probabilidad');
  await expect(page.getByRole('status').filter({ hasText: 'Temas encontrados' })).not.toContainText(
    '0 /',
  );
  await expect(page.locator('.help-topic-card')).toContainText('Probabilidad');
  await page.getByRole('button', { name: 'Limpiar búsqueda', exact: true }).click();
  const risk = help.topics.find((topic) => 'liveLegend' in topic)!;
  await page
    .getByRole('navigation', { name: 'Temas de ayuda' })
    .getByRole('button', { name: risk.title, exact: true })
    .click();
  await expect(page.locator('.help-live-legend li')).toHaveCount(config.leyenda.length);
  for (const level of config.leyenda)
    await expect(page.locator('.help-live-legend')).toContainText(level.etiqueta);
  await expect(page).toHaveURL(/ayuda_tema=riesgo/);
  await page.reload();
  await expect(page.locator('.help-live-legend')).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Soporte y capacitación', exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Descargar manual', exact: true }).click();
  expect((await download).suggestedFilename()).toBe('manual-usuario.pdf');
  const pdf = await page.request.get('/manual-usuario.pdf');
  expect(pdf.ok()).toBe(true);
  expect((await pdf.body()).subarray(0, 5).toString()).toBe('%PDF-');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.evaluate(() => {
    (document.activeElement as HTMLElement)?.blur();
    window.scrollTo(0, 0);
  });
  if (process.env.WEB_SCREENSHOT_DIR)
    await page.screenshot({
      path: `${process.env.WEB_SCREENSHOT_DIR}/${testInfo.project.name}-help-${process.env.WEB_TEST_SOURCE || 'fixtures'}.png`,
      fullPage: true,
    });
});

test('help search tolerates accents and recovers from no matches without changing geographic filters', async ({
  page,
}) => {
  await page.goto('/ayuda?horizonte=2&provincia=2001&ayuda_buscar=zzzzsincoincidencias');
  await expect(page.getByRole('heading', { name: 'Sin coincidencias', exact: true })).toBeVisible();
  await page.getByRole('searchbox', { name: 'Buscar en la ayuda' }).fill('prediccion');
  await expect(page.getByRole('heading', { name: 'Sin coincidencias', exact: true })).toHaveCount(
    0,
  );
  await page.getByRole('button', { name: 'Limpiar búsqueda', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Temas encontrados' })).toContainText(
    `${help.topics.length} / ${help.topics.length}`,
  );
  await expect(page.getByLabel('Provincia', { exact: true })).toHaveValue('2001');
  await expect(page.getByRole('button', { name: /^2 semanas/ })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});

test('unavailable model horizons show an explicit state and allow another horizon', async ({
  page,
}) => {
  await page.route('**/api/v1/configuracion', async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.horizontes_disponibles = data.horizontes_disponibles.filter((h: number) => h !== 3);
    data.horizontes = data.horizontes.map((h: { horizonte: number }) =>
      h.horizonte === 3 ? { ...h, disponible: false, motivo: 'Sin modelo para comprobación' } : h,
    );
    await route.fulfill({ response, json: data });
  });
  await page.goto('/modelo?horizonte=2&modelo_bloque=temporada_2024');
  await expect(page.locator('.classification-metrics')).toBeVisible();
  await page.getByRole('button', { name: /^3 semanas/ }).click();
  await expect(
    page.getByRole('heading', { name: 'Modelo no disponible para este horizonte', exact: true }),
  ).toBeVisible();
  await expect(
    page.locator('.classification-metrics, .baseline-table, .importance-data'),
  ).toHaveCount(0);
  await expect(page.getByLabel('Bloque de evaluación')).toBeDisabled();
  await page.getByRole('button', { name: 'Ver desempeño a 4 semanas', exact: true }).click();
  await expect(page.locator('.classification-metrics')).toBeVisible();
  await expect(page.getByLabel('Bloque de evaluación')).toHaveValue('temporada_2024');
  await expect(
    page.locator('.horizon-performance tbody tr').filter({ hasText: '2 semanas' }),
  ).toContainText('clf-h2');
  await expect(
    page.locator('.horizon-performance tbody tr').filter({ hasText: '3 semanas' }),
  ).toContainText('No disponible');
});
