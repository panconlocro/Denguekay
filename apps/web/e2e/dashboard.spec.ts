import { test, expect } from '@playwright/test';

// These tests use the actual FastAPI fixture server on port 18000, via Vite's proxy.
test('published dashboard, geographic filters and district navigation', async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/?horizonte=2');
  await expect(page.getByText('Entorno de pruebas · muestra v0', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Distritos prioritarios' })).toBeVisible();
  await expect(page.getByText('Experimental: modelo no validado', { exact: true })).toBeVisible();
  await expect(page.getByText('Consulta histórica · objetivo iniciado')).toBeVisible();
  await expect(page.locator('.priorities tbody tr')).toHaveCount(3);
  await expect(page.locator('.leaflet-interactive').first()).toBeVisible();
  // Only what the API publishes: three regional indicators, and a series only for a chosen district.
  await expect(page.getByLabel('Indicadores de la región Piura').locator('.card')).toHaveCount(3);
  await expect(page.locator('body')).not.toContainText('Incidencia por 100 000');
  await expect(page.locator('body')).not.toContainText('Serie regional');
  await expect(page.getByRole('heading', { name: /^Serie temporal/ })).toHaveCount(0);
  await expect(page.getByRole('note', { name: 'Alcance de los filtros' })).not.toContainText(
    'cuatro',
  );
  if (process.env.WEB_SCREENSHOT_DIR)
    await page.screenshot({
      path: `${process.env.WEB_SCREENSHOT_DIR}/${testInfo.project.name}-dashboard.png`,
      fullPage: true,
    });
  await page.getByLabel('Provincia', { exact: true }).selectOption('2001');
  await expect(page.locator('.priorities tbody tr')).toHaveCount(1);
  await page.getByLabel('Distrito', { exact: true }).selectOption('200101');
  await expect(page.getByRole('heading', { name: 'Serie temporal · Piura' })).toBeVisible();
  await page.locator('.priorities').getByRole('link', { name: 'Piura', exact: true }).click();
  await expect(page).toHaveURL(/\/distritos\/200101/);
  await expect(page.getByRole('heading', { name: 'Serie temporal de casos' })).toBeVisible();
  await expect(page.locator('.detail-indicators').getByText('80 %', { exact: true })).toBeVisible();
  await expect(page.locator('body')).not.toHaveText(/Datos ilustrativos/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  expect(errors).toEqual([]);
});

test('unavailable horizon never displays cached predictions', async ({ page }) => {
  await page.goto('/?horizonte=2');
  await expect(page.locator('.priorities tbody tr')).toHaveCount(3);
  await page.getByRole('button', { name: '3 semanas' }).click();
  await expect(page.getByRole('heading', { name: 'Horizonte no disponible' })).toBeVisible();
  await expect(page.locator('.priorities')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '3 semanas' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});

test('503 replaces previous results and retry recovers', async ({ page }) => {
  await page.goto('/?horizonte=2');
  await expect(page.locator('.priorities tbody tr')).toHaveCount(3);
  await page.route('**/api/v1/predicciones?**', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({
        codigo: 'bd_no_disponible',
        mensaje: 'La base de datos no está disponible',
      }),
    }),
  );
  await page.getByRole('button', { name: '4 semanas' }).click();
  await expect(
    page.getByText('La base de datos no está disponible', { exact: true }),
  ).toBeVisible();
  await expect(page.locator('.priorities')).toHaveCount(0);
  await page.unroute('**/api/v1/predicciones?**');
  await page.getByRole('button', { name: 'Reintentar' }).click();
  await expect(page.locator('.priorities tbody tr')).toHaveCount(3);
});

test('navigation and assets remain usable at the target viewport', async ({ page }, testInfo) => {
  await page.goto('/?horizonte=2');
  await expect(page.locator('.priorities tbody tr')).toHaveCount(3);
  const nav = page.getByRole('navigation', {
    name: testInfo.project.name === 'mobile' ? 'Navegación móvil' : 'Navegación principal',
    exact: true,
  });
  await nav
    .getByRole('link', {
      name: testInfo.project.name === 'mobile' ? 'Avisos' : /Alertas tempranas/,
    })
    .click();
  await expect(page.getByRole('heading', { name: 'Avisos experimentales' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Ver detalle →' })).toBeVisible();
  await page.getByLabel('Estado de los avisos').selectOption('retirada');
  await expect(
    page.getByRole('heading', { name: 'Sin registros para esta selección' }),
  ).toBeVisible();
  const broken = await page
    .locator('img')
    .evaluateAll((images) =>
      images
        .filter((i) => !(i as HTMLImageElement).complete || !(i as HTMLImageElement).naturalWidth)
        .map((i) => (i as HTMLImageElement).src),
    );
  expect(broken).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  if (process.env.WEB_SCREENSHOT_DIR)
    await page.screenshot({
      path: `${process.env.WEB_SCREENSHOT_DIR}/${testInfo.project.name}-alerts.png`,
      fullPage: true,
    });
});

test('the three regional indicators fill their row without gaps', async ({ page }, info) => {
  await page.goto('/?horizonte=2');
  const group = page.getByLabel('Indicadores de la región Piura');
  await expect(group.locator('.card')).toHaveCount(3);
  const outer = (await group.boundingBox())!;
  const boxes = await Promise.all(
    [0, 1, 2].map((i) => group.locator('.card').nth(i).boundingBox()),
  );
  const [a, b, c] = boxes.map((box) => box!);
  const right = (box: { x: number; width: number }) => box.x + box.width;
  if (info.project.name === 'mobile') {
    expect(Math.abs(a.y - b.y)).toBeLessThan(1);
    expect(Math.abs(right(b) - (outer.x + outer.width))).toBeLessThan(2);
    expect(Math.abs(c.width - outer.width)).toBeLessThan(2);
  } else {
    expect(Math.abs(a.y - b.y) + Math.abs(b.y - c.y)).toBeLessThan(1);
    expect(Math.abs(right(c) - (outer.x + outer.width))).toBeLessThan(2);
  }
});

test('the dashboard bottom row uses the whole width until a district is chosen', async ({
  page,
}, info) => {
  await page.goto('/?horizonte=2');
  await expect(page.locator('.dashboard-bottom .card').first()).toBeVisible();
  const bottom = (await page.locator('.dashboard-bottom').boundingBox())!;
  const stack = (await page.locator('.dashboard-bottom .stack').boundingBox())!;
  expect(Math.abs(stack.width - bottom.width)).toBeLessThan(2);
  await page.getByLabel('Distrito', { exact: true }).selectOption('200101');
  await expect(page.getByRole('heading', { name: 'Serie temporal · Piura' })).toBeVisible();
  const after = (await page.locator('.dashboard-bottom .stack').boundingBox())!;
  if (info.project.name !== 'mobile') expect(after.width).toBeLessThan(bottom.width - 100);
});
