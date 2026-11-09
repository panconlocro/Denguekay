import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const views = [
  ['dashboard', '/?horizonte=2', '.priorities tbody tr'],
  ['map', '/mapa?horizonte=2', '.leaflet-interactive'],
  ['district', '/distritos/200101?horizonte=2', '.recharts-surface'],
  ['alerts', '/alertas?horizonte=2', '.alert-indicators'],
  ['models', '/modelo?horizonte=2', '.classification-metrics'],
  ['help', '/ayuda?horizonte=2&ayuda_tema=riesgo', '.help-live-legend'],
] as const;

for (const [name, url, ready] of views) {
  test(`accessibility and responsive layout: ${name}`, async ({ page }, testInfo) => {
    await page.goto(url);
    await expect(page.locator(ready).first()).toBeVisible();
    await expect(page.locator('.loading')).toHaveCount(0);
    const results = await new AxeBuilder({ page }).analyze();
    const report = {
      url,
      profile: process.env.WEB_TEST_SOURCE || 'fixtures',
      viewport: testInfo.project.name,
      axeVersion: results.testEngine.version,
      violations: results.violations,
      incomplete: results.incomplete.map(({ id, nodes }) => ({
        id,
        targets: nodes.map((n) => n.target),
      })),
      passedRules: results.passes.length,
    };
    await testInfo.attach('accessibility.json', {
      body: JSON.stringify(report, null, 2),
      contentType: 'application/json',
    });
    if (process.env.WEB_SCREENSHOT_DIR) {
      await mkdir(process.env.WEB_SCREENSHOT_DIR, { recursive: true });
      const prefix = `${testInfo.project.name}-${name}-${process.env.WEB_TEST_SOURCE || 'fixtures'}`;
      await writeFile(
        join(process.env.WEB_SCREENSHOT_DIR, `${prefix}-axe.json`),
        JSON.stringify(report, null, 2),
      );
      await page.screenshot({
        path: join(process.env.WEB_SCREENSHOT_DIR, `${prefix}-delivery.png`),
        fullPage: true,
      });
    }
    expect(results.violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
  });
}

test('keyboard skip link and navigation retain visible focus and geographic selection', async ({
  page,
}, testInfo) => {
  await page.goto('/?horizonte=2&provincia=2001');
  await expect(page.locator('.priorities tbody tr').first()).toBeVisible();
  await page.keyboard.press('Tab');
  const skip = page.getByRole('link', { name: 'Saltar al contenido', exact: true });
  await expect(skip).toBeFocused();
  await expect(skip).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main-content')).toBeFocused();
  const nav = page.getByRole('navigation', {
    name: testInfo.project.name === 'mobile' ? 'Navegación móvil' : 'Navegación principal',
    exact: true,
  });
  const link = nav.getByRole('link', {
    name: testInfo.project.name === 'mobile' ? 'Ayuda' : 'Ayuda y manual',
    exact: true,
  });
  await link.focus();
  expect(await link.evaluate((node) => getComputedStyle(node).outlineStyle)).not.toBe('none');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('searchbox', { name: 'Buscar en la ayuda' })).toBeVisible();
  await expect(page).toHaveTitle('Ayuda y manual · Denguekay');
  await expect(page.locator('#main-content')).toBeFocused();
  await expect(page.getByLabel('Provincia', { exact: true })).toHaveValue('2001');
  const search = page.getByRole('searchbox', { name: 'Buscar en la ayuda' });
  await search.fill('riesgo');
  await expect(search).toBeFocused();
  await page
    .getByRole('navigation', { name: 'Temas de ayuda' })
    .getByRole('button', { name: 'Riesgo y leyenda', exact: true })
    .press('Enter');
  await expect(page.locator('.help-topic-card h2')).toBeFocused();
});

test('320px layout and reduced motion remain usable', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/modelo?horizonte=2&modelo_bloque=temporada_2024');
  await expect(page.locator('.classification-metrics')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const comparison = page.getByRole('region', {
    name: 'Métricas comparadas por horizonte',
    exact: true,
  });
  await comparison.focus();
  await page.keyboard.press('ArrowRight');
  await expect.poll(() => comparison.evaluate((node) => node.scrollLeft)).toBeGreaterThan(0);
  await page.goto('/ayuda?horizonte=2');
  await expect(page.getByRole('searchbox', { name: 'Buscar en la ayuda' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('searchbox', { name: 'Buscar en la ayuda' }).fill('riesgo');
  await expect(page.locator('.help-live-legend')).toBeVisible();
});

test('not-found state has an accessible heading and return navigation', async ({ page }) => {
  await page.goto('/ruta-inexistente?horizonte=2');
  await expect(
    page.getByRole('heading', { name: 'Página no encontrada', exact: true, level: 2 }),
  ).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByRole('link', { name: 'Volver al tablero', exact: true }).click();
  await expect(page.locator('.priorities tbody tr').first()).toBeVisible();
});

test('dashboard does not display a retained probability from an unavailable prediction', async ({
  page,
}) => {
  const prediction = (
    await (await page.request.get('/api/v1/predicciones?ubigeo=200101&horizonte=2')).json()
  ).elementos[0];
  await page.route('**/api/v1/alertas?**', async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.total = 1;
    data.elementos = [
      {
        id_alerta: 777,
        ubigeo: '200101',
        distrito: 'Piura',
        horizonte: 2,
        nivel: 'muy_alto',
        nivel_etiqueta: 'Muy alto',
        estado: 'activa',
        cambio: 'nueva',
        fecha_generacion: '2026-11-04T23:00:00Z',
        fecha_retiro: null,
        motivo: null,
        experimental: true,
        prediccion: {
          ...prediction,
          disponible: false,
          estado: 'no_disponible',
          probabilidad_brote: 0.99,
        },
      },
    ];
    await route.fulfill({ response, json: data });
  });
  await page.goto('/?horizonte=2');
  await expect(page.locator('.alert-preview')).toContainText('Prob. Sin datos');
  await expect(page.locator('.alert-preview')).not.toContainText('99 %');
});
