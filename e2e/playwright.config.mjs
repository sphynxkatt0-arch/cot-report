import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: /worldclass.*\.spec\.mjs/,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  workers: process.env.CI ? 1 : undefined,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]] : 'list',
  use: {
    // The dashboard's documented local server defaults to 8000. Port 4173 is
    // commonly used by Vite projects on this workstation and can silently
    // point the suite at an unrelated app.
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:8000',
    browserName: 'chromium',
    headless: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure'
  }
});
