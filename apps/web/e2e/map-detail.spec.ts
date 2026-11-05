import { test, expect } from '@playwright/test';
import { number, percent } from '../src/lib/format';
import { shiftWeeks } from '../src/lib/series';

test('keyboard map selection opens coherent district details and all horizons', async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const response = await page.request.get('/api/v1/predicciones?ubigeo=200101&horizonte=2');
  const p = (await response.json()).elementos[0];
  const config = await (await page.request.get('/api/v1/configuracion')).json();
  await page.goto('/mapa?horizonte=2');
  const marker = page.getByRole('button', { name: /^Seleccionar Piura:/ });
  await expect(marker).toBeVisible();
  await marker.focus();
  await marker.press('Enter');
  await expect(page).toHaveURL(/\/mapa\?.*seleccion=200101/);
  await expect(page.getByLabel('Distrito del panel')).toHaveValue('200101');
  await expect(marker).toBeFocused();
  await expect(marker).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.selected-risk')).toContainText(percent(p.probabilidad_brote));
  await expect(page.locator('.district-facts')).toContainText(
    `≈ ${number(p.casos_estimados, 2)} casos`,
  );
  await page.evaluate(() => {
    (document.activeElement as HTMLElement | null)?.blur();
    window.scrollTo(0, 0);
  });
  if (process.env.WEB_SCREENSHOT_DIR)
    await page.screenshot({
      path: `${process.env.WEB_SCREENSHOT_DIR}/${info.project.name}-${process.env.WEB_TEST_SOURCE || 'fixtures'}-map.png`,
      fullPage: true,
    });
  await page.getByRole('link', { name: 'Ver detalle y serie temporal →' }).click();
  await expect(page).toHaveURL(/\/distritos\/200101/);
  await expect(page.locator('.detail-indicators')).toContainText(percent(p.probabilidad_brote));
  await expect(page.locator('.detail-indicators')).toContainText(
    'Umbral de la semana objetivo: no publicado',
  );
  await expect(page.getByRole('heading', { name: 'Contexto observado en el corte' })).toBeVisible();
  await expect(page.locator('.horizon-comparison tbody tr')).toHaveCount(config.horizontes.length);
  await expect(page.locator('.district-bottom .district-facts')).toBeVisible();
  await expect(page.locator('.recharts-surface').first()).toBeVisible();
  await page.getByText('Ver datos de la serie en tabla', { exact: true }).click();
  await expect(page.locator('.series-data tbody tr')).toHaveCount(26);
  await expect(page.locator('.series-data tbody tr').last().locator('td').nth(2)).toHaveText(
    'No disponible',
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.evaluate(() => {
    (document.activeElement as HTMLElement | null)?.blur();
    window.scrollTo(0, 0);
  });
  if (process.env.WEB_SCREENSHOT_DIR)
    await page.screenshot({
      path: `${process.env.WEB_SCREENSHOT_DIR}/${info.project.name}-${process.env.WEB_TEST_SOURCE || 'fixtures'}-detail.png`,
      fullPage: true,
    });
  await page
    .locator('.segments')
    .getByRole('button', { name: /^3 semanas/ })
    .click();
  if (config.horizontes.find((h: { horizonte: number }) => h.horizonte === 3).disponible) {
    const next = (
      await (await page.request.get('/api/v1/predicciones?ubigeo=200101&horizonte=3')).json()
    ).elementos[0];
    await expect(page.locator('.detail-indicators')).toContainText(
      `≈ ${number(next.casos_estimados, 2)} casos`,
    );
  } else {
    await expect(
      page.getByRole('heading', { name: 'Horizonte no disponible', exact: true }),
    ).toBeVisible();
    await expect(page.locator('.detail-indicators .metric-value')).toHaveCount(0);
    await expect(page.locator('.chart')).toHaveCount(0);
  }
  expect(errors).toEqual([]);
});

test('series ranges validate locally, persist on reload and retain their weekly alignment', async ({
  page,
}) => {
  const baseline = await (await page.request.get('/api/v1/series/200101?horizonte=2')).json();
  await page.goto('/distritos/200101?horizonte=2');
  await expect(page.locator('.chart')).toBeVisible();
  await page.getByRole('button', { name: '52 semanas', exact: true }).click();
  await page.getByText('Ver datos de la serie en tabla', { exact: true }).click();
  await expect(page.locator('.series-data tbody tr')).toHaveCount(52);
  await expect(page).toHaveURL(/serie_ventana=52/);
  await page.getByRole('button', { name: 'Rango personalizado', exact: true }).click();
  await page.getByLabel('Inicio de la serie').fill(shiftWeeks(baseline.hasta, 1));
  await page.getByLabel('Fin de la serie').fill(baseline.hasta);
  await page.getByRole('button', { name: 'Aplicar rango', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('anterior o igual');
  await expect(page).toHaveURL(/serie_ventana=52/);
  await page.getByLabel('Inicio de la serie').fill(shiftWeeks(baseline.hasta, -3));
  await page.getByRole('button', { name: 'Aplicar rango', exact: true }).click();
  await expect(page).toHaveURL(/serie_ventana=custom/);
  await expect(page.getByText('Ver datos de la serie en tabla', { exact: true })).toBeVisible();
  const table = page.locator('.series-data');
  if (!(await table.isVisible()))
    await page.getByText('Ver datos de la serie en tabla', { exact: true }).click();
  await expect(page.locator('.series-data tbody tr')).toHaveCount(4);
  await page.reload();
  await page.getByText('Ver datos de la serie en tabla', { exact: true }).click();
  await expect(page.locator('.series-data tbody tr')).toHaveCount(4);
  await page
    .locator('.segments')
    .getByRole('button', { name: /^4 semanas/ })
    .click();
  await expect(page).toHaveURL(/horizonte=4/);
  await expect(page.locator('.series-data tbody tr')).toHaveCount(4);
});

test('unavailable map values stay grey and never expose carried probabilities or magnitudes', async ({
  page,
}) => {
  await page.route('**/api/v1/mapa-riesgo?**', async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    const p = data.features.find((f: { id: string }) => f.id === '200101').properties;
    Object.assign(p, {
      estado: 'no_disponible',
      motivo: 'Sin historia suficiente para esta comprobación',
      probabilidad_brote: 0.99,
      nivel_riesgo: 'muy_alto',
      casos_estimados: 999,
    });
    await route.fulfill({ response, json: data });
  });
  await page.goto('/mapa?horizonte=2&seleccion=200101');
  const marker = page.getByRole('button', { name: 'Seleccionar Piura: Sin datos', exact: true });
  await expect(marker).toHaveAttribute('fill', '#a5abb2');
  await expect(marker).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.selected-risk')).toContainText('Sin datos');
  await expect(page.locator('.selected-risk')).not.toContainText('99 %');
  await expect(page.locator('.district-facts')).not.toContainText('999');
  await expect(page.locator('.missing-districts')).toContainText('Piura');
});

test('district prediction and series errors clear separately and recover without substitutions', async ({
  page,
}) => {
  const fail = (route: import('@playwright/test').Route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ codigo: 'bd_no_disponible', mensaje: 'Error controlado en detalle' }),
    });
  await page.route('**/api/v1/predicciones?**', (route) =>
    new URL(route.request().url()).searchParams.get('horizonte') === '2'
      ? fail(route)
      : route.continue(),
  );
  await page.route('**/api/v1/series/200101?**', fail);
  await page.goto('/distritos/200101?horizonte=2');
  await expect(page.locator('.detail-indicators').getByRole('alert')).toHaveCount(1);
  await expect(page.locator('.detail-indicators .metric-value')).toHaveCount(0);
  const series = page
    .locator('section.card')
    .filter({ has: page.getByRole('heading', { name: 'Serie temporal de casos', exact: true }) });
  await expect(series.getByRole('alert')).toHaveCount(1);
  await expect(series.locator('.chart')).toHaveCount(0);
  await page.unroute('**/api/v1/predicciones?**');
  await page.unroute('**/api/v1/series/200101?**');
  await page.locator('.detail-indicators').getByRole('button', { name: 'Reintentar' }).click();
  await series.getByRole('button', { name: 'Reintentar' }).click();
  await expect(page.locator('.detail-indicators .metric-value')).toHaveCount(2);
  await expect(series.locator('.chart')).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});
