// See docs/dev/resolved/E2E_AND_SCREENSHOTTING.md §4.2. Chromium-only, sequential, pointed at
// the fake-model server by default so it runs anywhere (CI, any dev machine/architecture) with
// no Docker and no real model weights.
import { defineConfig, devices } from '@playwright/test'

const PORT = 8319
const explicitUrl = process.env.PERSONA_FORGE_UI_URL
const baseURL = explicitUrl || `http://127.0.0.1:${PORT}`

export default defineConfig({
  testDir: '.',
  testMatch: '**/*.spec.js',
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL,
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // Only spin up the fake-model server ourselves when no explicit target was given (§7 points
  // PERSONA_FORGE_UI_URL at a real, already-running instance instead, e.g. over an SSH tunnel to
  // dockermisc1 — Playwright must not try to also start a fake server in that case).
  webServer: explicitUrl
    ? undefined
    : {
        command: `node run-server.mjs ${PORT}`,
        url: `${baseURL}/health`,
        reuseExistingServer: !process.env.CI,
        timeout: 30_000,
      },
})
