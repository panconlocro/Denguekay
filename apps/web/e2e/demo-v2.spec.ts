import { test, expect } from '@playwright/test';
import type { Prediction } from '../src/api/types';

function sorted(rows: Prediction[]) {
  return [...rows].sort(
    (a, b) =>
      (b.probabilidad_brote ?? -1) - (a.probabilidad_brote ?? -1) ||
      a.ubigeo.localeCompare(b.ubigeo),
  );
}

// The dedicated profile targets the read-only API over the generated demo, never fixture values.
test('local v2 predictions, horizon switching and district series', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const config = await (await page.request.get('/api/v1/configuracion')).json();
  expect(config.horizontes_disponibles).toEqual([2, 3, 4]);
  await page.goto('/');
  await expect(page.getByText('Demo local v2 · experimental', { exact: true })).toBeVisible();
  await expect(page.getByText('Consulta histórica · objetivo iniciado')).toBeVisible();
  await expect(page.getByRole('note', { name: 'Procedencia de los datos' })).toContainText(
    'Corte de datos: 27/12/2025',
  );
  for (const horizon of [4, 3, 2]) {
    const response = await page.request.get(
      `/api/v1/predicciones?horizonte=${horizon}&tamano_pagina=100`,
    );
    expect(response.ok()).toBe(true);
    const predictions = await response.json();
    expect(predictions.total).toBe(65);
    expect(predictions.elementos.every((p: { disponible: boolean }) => p.disponible)).toBe(true);
    await page.getByRole('button', { name: `${horizon} semanas` }).click();
    await expect(page.getByRole('button', { name: `${horizon} semanas` })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(page.locator('.priorities tbody tr')).toHaveCount(9);
    await expect(page.getByText('Se muestran 9 de 65 distritos', { exact: false })).toBeVisible();
    const first = sorted(predictions.elementos)[0];
    await expect(page.locator('.priorities tbody tr').first()).toContainText(first.distrito);
  }
  await expect(page.getByRole('heading', { name: 'Sin avisos experimentales' })).toBeVisible();
  await expect(
    page.getByRole('region', { name: 'Vigencia y anticipación de las predicciones' }),
  ).toContainText('Sin anticipación');
  await expect(page.locator('.leaflet-interactive').first()).toBeVisible();
  expect(
    await page
      .locator('.dashboard-top .map-frame')
      .evaluate((frame) =>
        Math.abs(frame.clientHeight - frame.querySelector('.risk-map')!.clientHeight),
      ),
  ).toBeLessThanOrEqual(2);
  expect(
    await page.locator('img[src^="/assets/"]:visible').evaluateAll((images) =>
      images.every((image) => {
        const img = image as HTMLImageElement;
        const bounds = img.getBoundingClientRect();
        const sizes: Record<string, number[]> = {
          'logo.svg': [34, 34],
          'map.svg': [18, 18],
          'series.svg': [18, 18],
          'alert.svg': [17.6, 15.6],
          'help-ring.svg': [16, 16],
        };
        const size = sizes[img.src.split('/').pop()!];
        return (
          img.complete &&
          img.naturalWidth > 0 &&
          !!size &&
          Math.abs(bounds.width - size[0]) < 0.1 &&
          Math.abs(bounds.height - size[1]) < 0.1
        );
      }),
    ),
  ).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  if (process.env.WEB_SCREENSHOT_DIR)
    await page.screenshot({
      path: `${process.env.WEB_SCREENSHOT_DIR}/${testInfo.project.name}-demo-v2.png`,
      fullPage: true,
    });
  await page.getByLabel('Distrito', { exact: true }).selectOption('200101');
  await expect(page.locator('.priorities tbody tr')).toHaveCount(1);
  await page.locator('.priorities').getByRole('link', { name: 'Piura', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Serie temporal de casos' })).toBeVisible();
  await expect(page.locator('.detail-indicators')).toContainText('intervalo nominal 80 %');
  await expect(page.locator('.recharts-surface').first()).toBeVisible();
  expect(errors).toEqual([]);
});

test('all 65 priorities remain accessible and geographic filters preserve regional indicators', async ({
  page,
}) => {
  const data = await (
    await page.request.get('/api/v1/predicciones?horizonte=2&tamano_pagina=100')
  ).json();
  const summary = await (await page.request.get('/api/v1/tablero/resumen?horizonte=2')).json();
  await page.goto('/?horizonte=2');
  const pager = page.getByRole('navigation', {
    name: 'Páginas de distritos prioritarios',
    exact: true,
  });
  const seen: string[] = [];
  for (let n = 1; n <= 8; n++) {
    await expect(pager).toContainText(`Página ${n} de 8`);
    const links = await page
      .locator('.priorities tbody a')
      .evaluateAll((elements) =>
        elements.map((e) => e.getAttribute('href')!.match(/distritos\/(\d{6})/)![1]),
      );
    seen.push(...links);
    if (n < 8) await pager.getByRole('button', { name: 'Siguiente', exact: true }).click();
  }
  expect(seen).toEqual(sorted(data.elementos).map((p) => p.ubigeo));
  await expect(pager.getByRole('button', { name: 'Siguiente', exact: true })).toBeDisabled();
  const indicators = page.getByLabel('Indicadores de la región Piura');
  const magnitude = indicators.locator('.card').nth(2).locator('.metric-value');
  await expect(magnitude).toHaveText(
    `≈ ${String(summary.casos_estimados_region.valor).replace('.', ',')}`,
  );
  const regionalValues = await indicators.locator('.metric-value').allTextContents();
  await page.getByLabel('Provincia', { exact: true }).selectOption('2001');
  await expect(pager).toContainText('Página 1 de 2');
  await expect(page.getByRole('note', { name: 'Alcance de los filtros' })).toContainText(
    'no modifican los cuatro indicadores regionales',
  );
  expect(await indicators.locator('.metric-value').allTextContents()).toEqual(regionalValues);
  await page.getByLabel('Distrito', { exact: true }).selectOption('200101');
  await expect(page.locator('.priorities tbody tr')).toHaveCount(1);
  await expect(pager).toHaveCount(0);
  await page.getByRole('button', { name: /^3 semanas/ }).click();
  await expect(page.locator('.priorities tbody tr')).toHaveCount(1);
  await expect(page.getByRole('button', { name: /^3 semanas/ })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});

test('partial magnitudes and absent counts never become a complete regional total', async ({
  page,
}) => {
  await page.route('**/api/v1/predicciones?**', async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.elementos[0].casos_estimados = null;
    const target = new Date(`${data.elementos[0].semana_objetivo.fecha_inicio}T00:00:00-05:00`);
    for (const p of data.elementos)
      p.fecha_generacion = new Date(target.getTime() - 7 * 86400000).toISOString();
    await route.fulfill({ response, json: data });
  });
  await page.route('**/api/v1/tablero/resumen?**', async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.casos_observados_ultima_semana.valor = null;
    delete data.niveles_riesgo.alto;
    await route.fulfill({ response, json: data });
  });
  await page.goto('/?horizonte=2');
  const indicators = page.getByLabel('Indicadores de la región Piura');
  await expect(indicators.locator('.card').nth(2)).toContainText('Cobertura incompleta: 64 de 65');
  await expect(indicators.locator('.metric-value')).toHaveText([
    'No disponible',
    'No disponible',
    'No disponible',
    'No disponible',
  ]);
  await expect(
    page.getByRole('region', { name: 'Vigencia y anticipación de las predicciones' }),
  ).toContainText('No alcanza el mínimo de 2 semanas');
  await expect(page.locator('.priorities tbody tr')).toHaveCount(9);
  await expect(page.locator('body')).not.toContainText('≈ No disponible');
});

test('failed summary and map clear their results while the priorities remain usable', async ({
  page,
}) => {
  await page.goto('/?horizonte=2');
  await expect(page.locator('.priorities tbody tr')).toHaveCount(9);
  const fail = (route: import('@playwright/test').Route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({
        codigo: 'bd_no_disponible',
        mensaje: 'Error controlado de comprobación',
      }),
    });
  await page.route('**/api/v1/tablero/resumen?**', fail);
  await page.route('**/api/v1/mapa-riesgo?**', fail);
  await page.getByRole('button', { name: /^3 semanas/ }).click();
  await expect(page.getByRole('alert')).toHaveCount(2);
  await expect(page.getByLabel('Indicadores de la región Piura')).toHaveCount(0);
  await expect(page.locator('.leaflet-container')).toHaveCount(0);
  await expect(page.locator('.priorities tbody tr')).toHaveCount(9);
  await page.unroute('**/api/v1/tablero/resumen?**');
  await page.unroute('**/api/v1/mapa-riesgo?**');
  await page.getByRole('button', { name: 'Reintentar', exact: true }).first().click();
  await expect(page.getByRole('button', { name: 'Reintentar', exact: true })).toHaveCount(1);
  await page.getByRole('button', { name: 'Reintentar', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.locator('.leaflet-interactive').first()).toBeVisible();
  await expect(page.getByLabel('Indicadores de la región Piura')).toBeVisible();
});

test('unknown geographic URLs are explicit and clearable', async ({ page }) => {
  await page.goto('/?horizonte=2&provincia=9999&distrito=200101');
  await expect(page.getByRole('heading', { name: 'Selección geográfica no válida' })).toHaveCount(
    4,
  );
  await expect(page.locator('.priorities')).toHaveCount(0);
  await expect(page.locator('.leaflet-container')).toHaveCount(0);
  await expect(page.getByLabel('Provincia', { exact: true })).toHaveValue('9999');
  await expect(page.getByLabel('Distrito', { exact: true })).toHaveValue('200101');
  await page.getByRole('button', { name: 'Limpiar filtros', exact: true }).click();
  await expect(page.locator('.priorities tbody tr')).toHaveCount(9);
  await expect(page.getByRole('heading', { name: 'Selección geográfica no válida' })).toHaveCount(
    0,
  );
});

test('demo label is withheld when the connected API selects another model', async ({ page }) => {
  await page.route('**/api/v1/modelos/activo', async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.elementos[0].codigo = 'v0-clf-h2-1';
    await route.fulfill({ response, json: data });
  });
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText(
    'La API no corresponde a la demo experimental v2 esperada',
  );
  await expect(page.getByText('Demo local v2 · experimental', { exact: true })).toHaveCount(0);
  await expect(page.locator('.priorities')).toHaveCount(0);
  await page.unroute('**/api/v1/modelos/activo');
  await page.getByRole('button', { name: 'Reintentar' }).click();
  await expect(page.getByText('Demo local v2 · experimental', { exact: true })).toBeVisible();
  await expect(page.locator('.priorities tbody tr')).toHaveCount(9);
});
