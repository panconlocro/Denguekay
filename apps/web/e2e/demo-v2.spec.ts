import { test, expect } from '@playwright/test';

// The dedicated profile targets the read-only API over the generated demo, never fixture values.
test('local v2 predictions, horizon switching and district series', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const config = await (await page.request.get('/api/v1/configuracion')).json();
  expect(config.horizontes_disponibles).toEqual([2, 3, 4]);
  await page.goto('/');
  await expect(page.getByText('Demo local v2 · experimental', { exact: true })).toBeVisible();
  await expect(page.getByText('Consulta histórica · objetivo pasado')).toBeVisible();
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
    const first = [...predictions.elementos].sort(
      (a, b) => b.probabilidad_brote - a.probabilidad_brote,
    )[0];
    await expect(page.locator('.priorities tbody tr').first()).toContainText(first.distrito);
  }
  await expect(page.getByRole('heading', { name: 'Sin avisos experimentales' })).toBeVisible();
  await expect(page.locator('.leaflet-interactive').first()).toBeVisible();
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
