import { test, expect, type Page } from '@playwright/test';
import type { Alert, Prediction } from '../src/api/types';

// Synthetic records exist only in intercepted browser responses. Both actual APIs remain read-only.
async function alertScenario(page: Page) {
  const p: Prediction = (
    await (await page.request.get('/api/v1/predicciones?ubigeo=200101&horizonte=2')).json()
  ).elementos[0];
  function make(id: number, retired = false): Alert {
    const ubigeo = retired || id % 2 ? '200101' : '200501';
    const district = ubigeo === '200101' ? 'Piura' : 'Paita';
    return {
      id_alerta: id,
      ubigeo,
      distrito: district,
      horizonte: 2,
      nivel: !retired && id % 3 === 0 ? 'muy_alto' : 'alto',
      nivel_etiqueta: !retired && id % 3 === 0 ? 'Muy alto' : 'Alto',
      estado: retired ? 'retirada' : 'activa',
      cambio: 'nueva',
      fecha_generacion: '2026-11-04T23:00:00Z',
      fecha_retiro: retired && id !== 1011 ? '2026-11-05T01:00:00Z' : null,
      motivo: retired ? 'Retiro de comprobación' : null,
      experimental: true,
      prediccion: {
        ...p,
        ubigeo,
        distrito: district,
        disponible: true,
        estado: 'disponible',
        probabilidad_brote: retired ? 0.2 : id === 135 ? 0.99 : 0.5 + id / 1000,
        nivel_riesgo: retired ? 'bajo' : 'alto',
        nivel_riesgo_etiqueta: retired ? 'Bajo' : 'Alto',
        experimental: true,
      },
    };
  }
  const active = Array.from({ length: 135 }, (_, i) => make(i + 1));
  const retired = Array.from({ length: 12 }, (_, i) => make(1000 + i, true));
  const control = { failSecondPage: false, failDetail: false, secondPageReads: 0 };
  await page.route('**/api/v1/alertas**', async (route) => {
    const url = new URL(route.request().url());
    const detail = url.pathname.match(/\/alertas\/(\d+)$/);
    if (detail) {
      if (control.failDetail)
        return route.fulfill({
          status: 503,
          json: { codigo: 'bd_no_disponible', mensaje: 'Detalle temporalmente no disponible' },
        });
      const record = [...active, ...retired].find((a) => a.id_alerta === Number(detail[1]));
      return route.fulfill(
        record
          ? { status: 200, json: record }
          : { status: 404, json: { codigo: 'alerta_no_encontrada', mensaje: 'Sin registro' } },
      );
    }
    const state = url.searchParams.get('estado');
    const rows = (state === 'retirada' ? retired : active).filter(
      (a) => a.horizonte === Number(url.searchParams.get('horizonte')),
    );
    const n = Number(url.searchParams.get('pagina') || 1);
    if (state === 'activa' && n === 2) {
      control.secondPageReads++;
      if (control.failSecondPage)
        return route.fulfill({
          status: 503,
          json: {
            codigo: 'bd_no_disponible',
            mensaje: 'Segunda página temporalmente no disponible',
          },
        });
    }
    return route.fulfill({
      status: 200,
      json: {
        disponible: true,
        motivo: null,
        fecha_corte_datos: p.semana_corte.fecha_fin,
        fecha_actualizacion: p.fecha_generacion,
        elementos: rows.slice((n - 1) * 100, n * 100),
        total: rows.length,
        pagina: n,
        tamano_pagina: 100,
      },
    });
  });
  return control;
}

test('published alert history remains factual for the actual connected API', async ({
  page,
}, info) => {
  const data = await (
    await page.request.get('/api/v1/alertas?horizonte=2&estado=activa&tamano_pagina=100')
  ).json();
  await page.goto('/alertas?horizonte=2');
  const stats = page.getByLabel('Resumen de registros filtrados');
  await expect(stats.locator('.metric-value').first()).toHaveText(String(data.total));
  await expect(stats.locator('.card').last()).toContainText('No disponible');
  await expect(page.locator('.target-field')).toContainText('SE ');
  if (data.total) {
    await expect(page.locator('.alerts-table tbody tr')).toHaveCount(Math.min(10, data.total));
    if (info.project.name === 'mobile')
      expect(
        await page
          .locator('.alerts-table')
          .evaluate((table) => table.scrollWidth <= table.parentElement!.clientWidth + 1),
      ).toBe(true);
  } else
    await expect(
      page.getByRole('heading', { name: 'Sin registros para esta selección', exact: true }),
    ).toBeVisible();
  if (process.env.WEB_SCREENSHOT_DIR) {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: `${process.env.WEB_SCREENSHOT_DIR}/${info.project.name}-${process.env.WEB_TEST_SOURCE || 'fixtures'}-alerts.png`,
      fullPage: true,
    });
  }
  if (data.total) {
    await page
      .locator('.alerts-table')
      .getByRole('link', { name: 'Ver detalle →' })
      .first()
      .click();
    await expect(page.getByRole('heading', { name: /Aviso experimental #/ })).toBeVisible();
    await expect(
      page.getByText(
        'Registro experimental: no constituye una alerta operativa ni genera notificaciones.',
      ),
    ).toBeVisible();
    if (process.env.WEB_SCREENSHOT_DIR) {
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({
        path: `${process.env.WEB_SCREENSHOT_DIR}/${info.project.name}-${process.env.WEB_TEST_SOURCE || 'fixtures'}-alert-detail.png`,
        fullPage: true,
      });
    }
    await page.getByRole('link', { name: 'Volver al listado', exact: true }).click();
  } else {
    await page.goto('/alertas/2147483647?horizonte=2');
    await expect(
      page.getByRole('heading', { name: 'Registro no encontrado', exact: true }),
    ).toBeVisible();
    await page.getByRole('link', { name: 'Volver al listado', exact: true }).click();
  }
  await page.getByLabel('Estado de los avisos').selectOption('retirada');
  await expect(page).toHaveURL(/aviso_estado=retirada/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});

test('all backend pages are sorted before UI paging and filters survive detail navigation', async ({
  page,
}) => {
  await alertScenario(page);
  await page.goto('/alertas?horizonte=2');
  const pager = page.getByRole('navigation', { name: 'Páginas de avisos', exact: true });
  await expect(page.locator('.alerts-table tbody tr').first().getByRole('link')).toHaveAttribute(
    'href',
    /\/alertas\/135\?/,
  );
  const seen: string[] = [];
  for (let n = 1; n <= 14; n++) {
    await expect(pager).toContainText(`página ${n} de 14`);
    seen.push(
      ...(await page
        .locator('.alerts-table tbody a')
        .evaluateAll((links) =>
          links.map((a) => a.getAttribute('href')!.match(/alertas\/(\d+)/)![1]),
        )),
    );
    if (n < 14) await pager.getByRole('button', { name: 'Siguiente', exact: true }).click();
  }
  expect(new Set(seen).size).toBe(135);
  await expect(pager.getByRole('button', { name: 'Siguiente', exact: true })).toBeDisabled();
  await page.getByLabel('Nivel de los avisos').selectOption('muy_alto');
  await expect(pager).toContainText('45 registros · página 1 de 5');
  await pager.getByRole('button', { name: 'Siguiente', exact: true }).click();
  await page.getByLabel('Provincia', { exact: true }).selectOption('2001');
  await expect(pager).toContainText('página 1');
  await expect(page).not.toHaveURL(/aviso_pagina=/);
  await page.reload();
  await expect(page.getByLabel('Nivel de los avisos')).toHaveValue('muy_alto');
  await page.getByLabel('Nivel de los avisos').selectOption('');
  await page.getByLabel('Estado de los avisos').selectOption('retirada');
  await expect(pager).toContainText('12 registros');
  await page.locator('.alerts-table').getByRole('link', { name: 'Ver detalle →' }).first().click();
  await expect(page.getByRole('heading', { name: /Aviso experimental #1011/ })).toBeVisible();
  await expect(page.locator('.district-facts')).toContainText('Sin fecha publicada');
  await expect(page.locator('.district-facts')).toContainText('Retiro de comprobación');
  await expect(page.locator('.alert-detail-values .metric-value').first()).toHaveText('20 %');
  await page.getByRole('link', { name: 'Volver al listado', exact: true }).click();
  await expect(page.getByLabel('Estado de los avisos')).toHaveValue('retirada');
  await expect(page.getByLabel('Provincia', { exact: true })).toHaveValue('2001');
  await expect(page.getByLabel('Distrito', { exact: true })).toHaveValue('');
});

test('a failed later page never becomes a partial total and detail errors recover', async ({
  page,
}) => {
  const control = await alertScenario(page);
  control.failSecondPage = true;
  await page.goto('/alertas?horizonte=2');
  const list = page.locator('#alerts-list');
  await expect(list.getByRole('alert')).toContainText('Segunda página temporalmente no disponible');
  await expect(page.locator('.alerts-table')).toHaveCount(0);
  const stats = page.getByLabel('Resumen de registros filtrados');
  await expect(stats.locator('.metric-value').first()).toHaveText('No disponible');
  await expect(stats.locator('.metric-value').nth(2)).toHaveText('12');
  control.failSecondPage = false;
  await list.getByRole('button', { name: 'Reintentar', exact: true }).click();
  await expect(stats.locator('.metric-value').first()).toHaveText('135');
  expect(control.secondPageReads).toBeGreaterThanOrEqual(2);
  control.failDetail = true;
  await page.locator('.alerts-table').getByRole('link', { name: 'Ver detalle →' }).first().click();
  await expect(page.getByRole('alert')).toContainText('Detalle temporalmente no disponible');
  await expect(page.locator('.alert-detail-values')).toHaveCount(0);
  control.failDetail = false;
  await page.getByRole('button', { name: 'Reintentar', exact: true }).click();
  await expect(page.locator('.alert-detail-values')).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('invalid filters are explicit and a deep link aligns to its own record', async ({ page }) => {
  await alertScenario(page);
  await page.goto('/alertas?horizonte=2&aviso_estado=invalido');
  await expect(
    page.getByRole('heading', { name: 'Filtros de avisos no válidos', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Restablecer filtros de avisos', exact: true }).click();
  await expect(page.locator('.alerts-table tbody tr')).toHaveCount(10);
  await page.goto('/alertas/abc?horizonte=2');
  await expect(
    page.getByRole('heading', { name: 'Identificador de aviso no válido', exact: true }),
  ).toBeVisible();
  await page.goto('/alertas/135?horizonte=4&provincia=9999&distrito=999999&aviso_estado=retirada');
  await expect(page).toHaveURL(
    (url) =>
      url.searchParams.get('horizonte') === '2' &&
      url.searchParams.get('distrito') === '200101' &&
      url.searchParams.get('provincia') === '2001' &&
      url.searchParams.get('aviso_estado') === 'activa',
  );
  await expect(page.getByRole('heading', { name: /Aviso experimental #135/ })).toBeVisible();
  await page
    .locator('.segments')
    .getByRole('button', { name: /^4 semanas/ })
    .click();
  await expect(page).toHaveURL(
    (url) => url.pathname === '/alertas' && url.searchParams.get('horizonte') === '4',
  );
  await expect(page.locator('.alert-detail-values')).toHaveCount(0);
  await expect(
    page.getByRole('heading', { name: 'Sin registros para esta selección', exact: true }),
  ).toBeVisible();
});
