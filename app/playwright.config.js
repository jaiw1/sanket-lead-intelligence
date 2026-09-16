import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end against a REAL backend.
 *
 * These specs exist to prove the things a component test cannot: that an RM's queue is
 * scoped by the server and not by the browser, that a 403 on a manager-only action is a
 * 403, that the CRM push takes two deliberate steps, and that a dead session ends up on
 * the login screen with an explanation.
 *
 * Prerequisites (see e2e/README.md):
 *   1. `uvicorn app.main:app --port 8001` in rrsquad-platform, with its Postgres up
 *   2. a published SANKET run: `python -m app.fixtures load --product sanket --source fixture`
 *   3. the demo users seeded with a known initial password:
 *      `SEED_INITIAL_PASSWORD=… python -m app.seeds --reset-passwords`
 *
 * The web server is vite's dev server, which proxies /api to 8001 so the session cookie
 * stays same-origin — exactly as the nginx deploy does.
 */
const PORT = 5191

export default defineConfig({
  testDir: './e2e',
  // Sessions, assignment and consent are shared server state: two workers racing over the
  // same five demo users would flake for reasons that have nothing to do with the UI.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  globalSetup: './e2e/global-setup.js',
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run dev',
    url: `http://localhost:${PORT}/login`,
    reuseExistingServer: true,
    timeout: 60_000,
  },
})
