import { defineConfig, devices } from '@playwright/test';

/**
 * E2e contra el stack REAL levantado con docker-compose (la imagen edge: SPA horneado
 * + gateway same-origin), no `ng serve` — se prueba el artefacto que se despliega.
 * El stack se arranca por fuera (`make e2e` / job de CI); aquí solo se apunta a él.
 * `E2E_BASE_URL` permite correr contra la VM de la demo si hace falta.
 */
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:8080';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
