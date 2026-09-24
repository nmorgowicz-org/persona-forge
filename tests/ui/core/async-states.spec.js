import { test, expect } from '@playwright/test'

// B-P9: crafted async states (empty → working → done/error) + the cold-boot splash.
//
// Four claims:
//
//   1. a success is *announced* — in one live region, not in whatever element happened to
//      re-render, so a screen reader hears it without moving focus;
//   2. a long generation *reports* — a progressbar whose aria-valuenow actually changes,
//      rather than a decorative bar that only looks determinate;
//   3. empty surfaces are designed — an illustration and exactly one next action, so an
//      empty Stitch Studio is not a dead end;
//   4. the 503 window is designed too — the first paint of a cold boot shows the Signal
//      Crucible mark over the startup field with a load readout.
//
// RED-first: none of these exist on unmodified code (no [data-testid="announcer"], no
// role="progressbar" on the Speak bar, no [data-testid="empty-state-action"], no
// [data-testid="startup-state"]).

const PROFILE = process.env.TEST_PROFILE ?? ''

test.describe('B-P9: crafted async states', () => {
  test('a completed generation is announced in a single live region', async ({ page }) => {
    await page.goto('/')

    // The region exists before anything happens to it -- a live region created *with* its
    // message is not reliably announced.
    const announcer = page.getByTestId('announcer')
    await expect(announcer).toHaveCount(1)
    await expect(announcer).toHaveAttribute('role', 'status')
    await expect(announcer).toBeEmpty()

    await page.getByTestId('speak-text-input').fill('Announce me.')
    await page.getByTestId('speak-generate-button').click()
    await expect(page.getByTestId('speak-result')).toBeVisible({ timeout: 30000 })

    await expect(announcer).not.toBeEmpty({ timeout: 10000 })
    await expect(announcer).toContainText(/ready|generated|complete/i)

    // Still the only one: a second region would mean two places claiming to speak for the app.
    await expect(page.getByTestId('announcer')).toHaveCount(1)
  })

  test('a long generation reports determinate progress on a progressbar', async ({ page }) => {
    // The default fake completes an async job the moment it is created, so there is no
    // window in which progress can be observed. Same gate as core/transport.spec.js.
    test.skip(PROFILE !== 'slow_async', 'needs TEST_PROFILE=slow_async: async jobs run 3-5s')

    await page.goto('/')
    await page.getByTestId('speak-text-input').fill('Progress me.')
    await page.getByTestId('speak-generate-button').click()

    const bar = page.getByRole('progressbar')
    await expect(bar).toBeVisible({ timeout: 15000 })

    const first = await bar.getAttribute('aria-valuenow')
    expect(first, 'progressbar has no aria-valuenow').not.toBeNull()

    // A bar that renders a percentage but never publishes it is not determinate; the value
    // must actually move.
    await expect
      .poll(async () => bar.getAttribute('aria-valuenow'), { timeout: 20000 })
      .not.toBe(first)

    await expect(bar).toHaveAttribute('aria-valuemax', '100')
  })

  test('an empty Stitch Studio offers an illustration and exactly one next action', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()

    const emptyState = page.getByTestId('empty-state')
    await expect(emptyState).toBeVisible({ timeout: 15000 })
    await expect(emptyState.locator('svg').first()).toBeVisible()

    const action = emptyState.getByTestId('empty-state-action')
    await expect(action).toHaveCount(1)
    await expect(action).toBeEnabled()
    await expect(action).not.toBeEmpty()
  })

  test('an empty library offers an illustration and exactly one next action', async ({ page }) => {
    // The fixture library is populated, so emptiness is staged at the network boundary.
    // Shape matters: listVoices() unwraps `body.voices`.
    await page.route('**/voices', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"voices":[]}' }),
    )
    await page.route('**/omnivoice/segments', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"segments":[]}' }),
    )

    await page.goto('/')
    await page.getByTestId('nav-voice-library').click()

    const emptyState = page.getByTestId('empty-state')
    await expect(emptyState).toBeVisible({ timeout: 15000 })
    await expect(emptyState.locator('svg').first()).toBeVisible()

    const action = emptyState.getByTestId('empty-state-action')
    await expect(action).toHaveCount(1)
    await expect(action).toBeEnabled()
    await expect(action).not.toBeEmpty()
  })

  test('the cold-boot window shows the Signal Crucible startup state', async ({ page }) => {
    // A cold boot is a 503 on /health: the poller leaves every store field at its initial
    // value, so the app knows nothing except that the service has never started.
    await page.route('**/health', (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'loading', error: 'service starting' }),
      }),
    )

    await page.goto('/')

    const splash = page.getByTestId('startup-state')
    await expect(splash).toBeVisible({ timeout: 15000 })
    await expect(splash.locator('img, svg').first()).toBeVisible()
    await expect(splash).toContainText(/load|start|model/i)
  })
})
