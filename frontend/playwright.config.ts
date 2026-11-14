import { defineConfig } from '@playwright/test'

/**
 * End-to-end tests drive the real game in a browser. They need the backend
 * (manage.py runserver) running on port 8000 with at least one world, and
 * the development player from .env (manage.py create_dev_player). The Vite
 * dev server is started here if it is not already running.
 *
 * They use the installed Microsoft Edge, so no browser download is needed.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 180_000,
  expect: { timeout: 30_000 },
  workers: 1,
  use: {
    baseURL: 'http://localhost:5173',
    channel: 'msedge',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 60_000,
  },
})
