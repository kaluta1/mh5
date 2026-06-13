import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright smoke-test configuration.
 * Requires the backend and frontend to be running locally:
 *   cd backend && uvicorn main:app --port 8001
 *   cd frontend && npm run dev
 * Then run: npx playwright test
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3001',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
