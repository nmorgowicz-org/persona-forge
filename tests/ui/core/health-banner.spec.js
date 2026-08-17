import { test, expect } from '@playwright/test'

// The top notification bar must track in-flight model loads end-to-end: a post-boot
// Base load shows "Loading model…" while in flight and clears when the load finishes;
// a startup failure resolves into a persistent error bar with the server's error text
// instead of spinning "Loading model…" forever.
//
// State is driven at runtime through the fake server's /_test/* control endpoints
// (see _install_test_controls in tests/ui/fixtures/fake_model_server.py), because the
// Playwright webServer runs ONE shared fake server for the whole suite.
test.describe('health banner', () => {
  const CLEAR_TIMEOUT = { timeout: 15_000 }

  test('base load shows "Loading model…" bar, then clears', async ({ page, request }) => {
    await page.goto('/')
    await expect(page.getByTestId('nav-speak')).toBeVisible()

    try {
      // Longer than the steady-state 5s /health poll interval so the load window cannot
      // end before the store's next poll (a 3s load can be fully missed).
      await request.post('/_test/simulate-base-load', { data: { duration_seconds: 8 } })

      // The store polls /health (1s while a load is in flight); the bar appears within a few polls.
      await expect(page.getByText('Loading model…')).toBeVisible({ timeout: 15_000 })

      // After the simulated load finishes, the next poll clears loadingMessage and the bar goes away.
      await expect(page.getByText('Loading model…')).toBeHidden(CLEAR_TIMEOUT)
    } finally {
      await request.post('/_test/reset-state')
    }
  })

  test('startup failure shows an error bar with the failure reason', async ({ page, request }) => {
    await page.goto('/')
    await expect(page.getByTestId('nav-speak')).toBeVisible()

    try {
      await request.post('/_test/simulate-startup-failure')

      await expect(page.getByText('Model failed to load: fake startup error')).toBeVisible()

      // The failure bar is persistent while /health keeps reporting the error.
      await page.waitForTimeout(2_500)
      await expect(page.getByText('Model failed to load: fake startup error')).toBeVisible()
    } finally {
      await request.post('/_test/reset-state')
    }

    // After the reset, the bar clears on the next poll.
    await expect(page.getByText('Model failed to load')).toBeHidden(CLEAR_TIMEOUT)
  })
})
