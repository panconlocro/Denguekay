import { defineConfig } from '@playwright/test';

const demo = process.env.WEB_TEST_SOURCE === 'demo-v2';
export default defineConfig({
  testDir: './e2e',
  testMatch: demo
    ? ['demo-v2.spec.ts', 'map-detail.spec.ts', 'alerts.spec.ts', 'models-help.spec.ts']
    : ['dashboard.spec.ts', 'map-detail.spec.ts', 'alerts.spec.ts', 'models-help.spec.ts'],
  fullyParallel: false,
  workers: 2,
  use: {
    baseURL: 'http://127.0.0.1:5174',
    launchOptions: process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {},
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --port 5174',
    url: 'http://127.0.0.1:5174',
    reuseExistingServer: false,
    env: {
      API_PROXY_TARGET: `http://127.0.0.1:${demo ? 18001 : 18000}`,
      VITE_API_BASE_URL: '/api/v1',
      VITE_DATA_SOURCE: demo ? 'demo-v2' : 'fixtures',
    },
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1100 } } },
    {
      name: 'mobile',
      use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true },
    },
  ],
});
