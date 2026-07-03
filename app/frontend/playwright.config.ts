import { defineConfig, devices } from '@playwright/test';

const frontendUrl = process.env.PLAYWRIGHT_FRONTEND_URL || 'http://127.0.0.1:3017';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  reporter: [['line']],
  use: {
    baseURL: frontendUrl,
    channel: 'msedge',
    headless: true,
    ignoreHTTPSErrors: true,
    trace: 'retain-on-failure',
    screenshot: 'off',
    video: 'off',
  },
  projects: [
    {
      name: 'desktop',
      use: {
        viewport: { width: 1440, height: 1080 },
      },
    },
    {
      name: 'mobile',
      use: {
        browserName: 'chromium',
        ...devices['iPhone 13'],
        channel: 'msedge',
      },
    },
  ],
});
