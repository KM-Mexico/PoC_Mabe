import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: process.env['BASE_URL'] ?? 'http://web',
    browserName: 'chromium',
    trace: 'retain-on-failure'
  },
  reporter: 'line'
});
