import { test, expect } from '@playwright/test'

// Coarse sanity checks, not real benchmarks — the fake-model server returns instantly, so this
// only catches gross regressions (e.g. render-blocking work added to the initial load), not
// backend latency. See docs/plans/20260702-e2e_and_screenshotting.md §4.4.
test.describe('performance', () => {
  test('home page becomes interactive quickly', async ({ page }) => {
    const start = Date.now()
    await page.goto('/')
    await expect(page.getByTestId('speak-text-input')).toBeVisible()
    expect(Date.now() - start).toBeLessThan(5000)
  })

  test('navigating between pages does not accumulate console errors', async ({ page }) => {
    const errors = []
    page.on('pageerror', (err) => errors.push(err))
    await page.goto('/')
    for (const testId of ['nav-voice-design', 'nav-voice-library', 'nav-integrations', 'nav-runtime', 'nav-speak']) {
      await page.getByTestId(testId).click()
    }
    expect(errors).toEqual([])
  })
})
