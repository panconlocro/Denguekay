import { test, expect, type Page } from '@playwright/test';
import { number, percent } from '../src/lib/format';
import { shiftWeeks } from '../src/lib/series';
import AxeBuilder from '@axe-core/playwright';

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
  await expect(page.locator('.leaflet-tooltip')).toBeVisible();
  await marker.press('Escape');
  await expect(page.locator('.leaflet-tooltip')).toHaveCount(0);
  await expect(marker).toBeFocused();
  await marker.press('Enter');
  await expect(page).toHaveURL(/\/mapa\?.*seleccion=200101/);
  await expect(page.getByLabel('Distrito del panel')).toHaveValue('200101');
  await expect(marker).toBeFocused();
  await expect(marker).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.selected-risk')).toContainText(percent(p.probabilidad_brote));
  await expect(page.locator('.district-facts')).toContainText(
    `≈ ${number(p.casos_estimados, 2)} casos`,
  );
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
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
  await expect(page.locator('body')).not.toContainText('Umbral de la semana objetivo');
  await expect(page.locator('body')).not.toContainText('Alcance de la interpretación');
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

test('district polygons show the limits, keep the legend and select with Enter', async ({
  page,
}) => {
  await page.route('**/api/v1/mapa-riesgo?**', async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    for (const f of data.features) {
      const [x, y] = f.geometry.coordinates;
      const d = 0.03;
      f.geometry = {
        type: 'Polygon',
        coordinates: [
          [
            [x - d, y - d],
            [x + d, y - d],
            [x + d, y + d],
            [x - d, y + d],
            [x - d, y - d],
          ],
        ],
      };
    }
    await route.fulfill({ response, json: data });
  });
  await page.goto('/mapa?horizonte=2');
  await expect(page.locator('.map-note')).toContainText('Límites distritales');
  await expect(page.locator('.map-note')).toContainText('CC BY-IGO 3.0');
  await expect(page.locator('.map-note')).not.toContainText('Centroides');
  await expect(page.locator('.leaflet-interactive')).toHaveCount(65);
  await expect(page.locator('.map-legend > div')).toHaveCount(5);
  const polygon = page.getByRole('button', { name: /^Seleccionar Piura:/ });
  await expect(polygon).toBeVisible();
  await polygon.focus();
  await polygon.press('Enter');
  await expect(page).toHaveURL(/\/mapa\?.*seleccion=200101/);
  await expect(polygon).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByLabel('Distrito del panel')).toHaveValue('200101');
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

test.describe('climate of the cutoff week', () => {
  type Row = Record<string, unknown>;
  const mockObservations = async (page: Page, change: (row: Row) => void) => {
    await page.route('**/api/v1/observaciones?**', async (route) => {
      const response = await route.fetch();
      const data = await response.json();
      for (const row of data.elementos) change(row);
      await route.fulfill({ response, json: data });
    });
  };
  const fact = (page: Page, label: string) =>
    page.locator('.district-bottom .district-facts').locator(`dt:text-is("${label}") + dd`);

  test('uses ERA5-Land and CHIRPS v3 when the API publishes them and names the source', async ({
    page,
  }) => {
    await mockObservations(page, (row) => {
      Object.assign(row, {
        temp_media_c: null,
        hum_rel_media_pct: null,
        precip_total_mm: null,
        temp_media_era5_land_c: 27.5,
        humedad_era5_land_pct: 58.25,
        lluvia_chirps_mm: 0,
      });
    });
    await page.goto('/distritos/200101?horizonte=2');
    await expect(fact(page, 'Temperatura media')).toContainText('27,5 °C');
    await expect(fact(page, 'Temperatura media')).toContainText('Fuente: ERA5-Land');
    await expect(fact(page, 'Humedad relativa media')).toContainText('58,25 %');
    await expect(fact(page, 'Precipitación total')).toContainText('0 mm');
    await expect(fact(page, 'Precipitación total')).toContainText('Fuente: CHIRPS v3');
  });

  test('keeps the older values when the API does not send the new fields yet', async ({ page }) => {
    await mockObservations(page, (row) => {
      for (const key of [
        'temp_media_era5_land_c',
        'humedad_era5_land_pct',
        'lluvia_chirps_mm',
        'fecha_era5_land_disponible',
        'fecha_chirps_disponible',
      ])
        delete row[key];
      Object.assign(row, { temp_media_c: 24, hum_rel_media_pct: 63, precip_total_mm: 1.5 });
    });
    await page.goto('/distritos/200101?horizonte=2');
    await expect(fact(page, 'Temperatura media')).toContainText('24 °C');
    await expect(fact(page, 'Humedad relativa media')).toContainText('63 %');
    await expect(fact(page, 'Precipitación total')).toContainText('1,5 mm');
  });

  test('says pending, or not available, but never shows a zero for a missing value', async ({
    page,
  }) => {
    await mockObservations(page, (row) => {
      Object.assign(row, {
        temp_media_c: null,
        hum_rel_media_pct: null,
        precip_total_mm: null,
        temp_media_era5_land_c: null,
        humedad_era5_land_pct: null,
        lluvia_chirps_mm: null,
        fecha_era5_land_disponible: '2000-01-01',
        fecha_chirps_disponible: '2999-01-01',
      });
    });
    await page.goto('/distritos/200101?horizonte=2');
    await expect(fact(page, 'Temperatura media')).toHaveText('No disponible');
    await expect(fact(page, 'Humedad relativa media')).toHaveText('No disponible');
    await expect(fact(page, 'Precipitación total')).toHaveText('Pendiente de publicación');
    await expect(page.locator('.district-bottom .district-facts')).not.toContainText('0 mm');
  });
});
