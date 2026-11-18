// Mide la carga de cada vista principal sobre el build de producción (`vite preview`), una a la vez.
//
// HU0016-3: 20 cargas por vista, cada una en un contexto de navegador nuevo (sin caché) y con la API local leyendo
// una BD temporal. El tiempo es el de `performance.now()` desde el inicio de la navegación hasta que la vista muestra
// su contenido principal (tabla, mapa, indicadores o encabezado). Criterio: p95 de cada vista < 10 s.
//
// Uso (desde apps/web, con la API y `npm run preview` ya levantados; ver docs/backend/sla_local_v4.md):
//   node tools/measure_load.mjs --base http://127.0.0.1:4173 --salida ../../docs/backend/sla_vistas_v4_local.json
// CHROME_PATH permite usar un Chrome instalado. La salida debe estar en docs/backend/ o models/ (nunca en data/).
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, relative, resolve, sep } from 'node:path';
import { platform, release } from 'node:os';
import { chromium } from '@playwright/test';

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : fallback;
};
const base = option('--base', 'http://127.0.0.1:4173').replace(/\/$/, '');
const repetitions = Number(option('--repeticiones', '20'));
const limitSeconds = Number(option('--limite', '10'));
const output = resolve(option('--salida', '../../docs/backend/sla_vistas_v4_local.json'));
const root = resolve('../..');
const inside = (folder) => !relative(resolve(root, folder), output).startsWith('..');
if (!inside('docs/backend') && !inside('models')) {
  throw new Error('La salida debe estar en docs/backend/ o models/; nunca en data/.');
}
if (!Number.isInteger(repetitions) || repetitions < 2)
  throw new Error('Se requieren al menos 2 repeticiones.');

const views = [
  {
    name: 'Tablero',
    path: '/?horizonte=2',
    ready: (page) => [
      page.locator('.priorities tbody tr').first(),
      page.locator('.leaflet-interactive').first(),
    ],
  },
  {
    name: 'Mapa',
    path: '/mapa?horizonte=2',
    ready: (page) => [page.locator('.leaflet-interactive').first()],
  },
  {
    name: 'Detalle del distrito',
    path: '/distritos/200101?horizonte=2',
    ready: (page) => [page.locator('.detail-indicators .metric-value').first()],
  },
  {
    name: 'Avisos',
    path: '/alertas?horizonte=2',
    ready: (page) => [
      page
        .locator('.alerts-table tbody tr')
        .first()
        .or(page.getByRole('heading', { name: 'Sin registros para esta selección' })),
    ],
  },
  {
    name: 'Desempeño del modelo',
    path: '/modelo?horizonte=2',
    ready: (page) => [page.locator('.metric-value').first()],
  },
  {
    name: 'Ayuda y manual',
    path: '/ayuda',
    ready: (page) => [page.getByRole('heading', { name: 'Ayuda y manual', exact: true, level: 1 })],
  },
];

const percentile = (values, proportion) => {
  const sorted = [...values].sort((a, b) => a - b);
  const position = (sorted.length - 1) * proportion;
  const low = Math.floor(position);
  const high = Math.ceil(position);
  return sorted[low] + (sorted[high] - sorted[low]) * (position - low);
};

const browser = await chromium.launch(
  process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {},
);
const results = [];
try {
  for (const view of views) {
    const durations = [];
    let errors = 0;
    for (let i = 0; i < repetitions; i += 1) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
      const page = await context.newPage();
      try {
        await page.goto(base + view.path, { waitUntil: 'load', timeout: 30000 });
        for (const locator of view.ready(page))
          await locator.waitFor({ state: 'visible', timeout: 30000 });
        durations.push(await page.evaluate(() => performance.now()));
      } catch (error) {
        errors += 1;
        console.error(`${view.name} #${i + 1}: ${error.message.split('\n')[0]}`);
      } finally {
        await context.close();
      }
    }
    const ok = durations.length === repetitions && errors === 0;
    results.push({
      vista: view.name,
      ruta: view.path,
      repeticiones: repetitions,
      duraciones_ms: durations.map((d) => Math.round(d)),
      p50_ms: durations.length ? Math.round(percentile(durations, 0.5)) : null,
      p95_ms: durations.length ? Math.round(percentile(durations, 0.95)) : null,
      max_ms: durations.length ? Math.round(Math.max(...durations)) : null,
      errores: errors,
      cumple: ok && percentile(durations, 0.95) < limitSeconds * 1000,
    });
  }
  const report = {
    fecha_medicion: new Date().toISOString(),
    criterio: 'HU0016-3: p95 de la carga de cada vista < 10 s, 20 cargas por vista, una a la vez',
    limite_segundos: limitSeconds,
    base,
    navegador: browser.version(),
    entorno: { plataforma: `${platform()} ${release()}`, node: process.version },
    metodo:
      'Build de producción servido con vite preview; contexto de navegador nuevo por carga (sin caché); tiempo desde el ' +
      'inicio de la navegación hasta que la vista muestra su contenido principal; API local sobre una BD temporal.',
    resultados: results,
    cumple: results.every((r) => r.cumple),
  };
  mkdirSync(dirname(output), { recursive: true });
  writeFileSync(output, JSON.stringify(report, null, 2) + '\n', 'utf-8');
  console.log(
    JSON.stringify({
      archivo: relative(root, output).split(sep).join('/'),
      p95_ms: Object.fromEntries(results.map((r) => [r.vista, r.p95_ms])),
      cumple: report.cumple,
    }),
  );
  process.exitCode = report.cumple ? 0 : 2;
} finally {
  await browser.close();
}
