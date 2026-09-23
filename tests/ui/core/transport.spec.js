import { test, expect } from '@playwright/test'

// A-9 (T1): the shared audio transport coordinator. The playback-focus registry (N6) grows
// into the app's one transport coordinator: every surface that can sound *registers* itself
// (kind + label), *claims* playback when it starts, and *reports* its position -- so there is
// a single answer to "what is audible right now, and where is it". Each surface keeps its own
// element, transport logic and playback contract; the coordinator only observes and arbitrates.
// Plan: docs/plans/20260922-premium_audio_plugin_ux.md section 4 T1; runbook card A-9.
//
// The readout the spec asserts on is the sr-only `transport-active-source` element AppShell
// renders on every page. It is written imperatively from the coordinator's notifications --
// never React state -- because position is reported per animation frame.
//
// RED-first: every test must fail on unmodified code because the feature is missing.

const PROFILE = (process.env.TEST_PROFILE || '').trim().toLowerCase()

const readout = (page) => page.getByTestId('transport-active-source')

async function openStudio(page) {
  await page.goto('/')
  await page.getByTestId('nav-stitch-studio').click()
}

async function insertSegments(page, n) {
  await openStudio(page)
  await page.getByTestId('stitch-picker-toggle-segments').click()
  const items = page.getByTestId('stitch-picker-item-segments')
  await expect(items.first()).toBeVisible()
  for (let i = 0; i < n; i++) await items.nth(i).click()
  await page.getByTestId('stitch-picker-insert-segments').click()
  await expect(page.getByTestId('stitch-clip')).toHaveCount(n)
}

test.describe('A-9: shared audio transport coordinator', () => {
  test('the coordinator reports the active source and its position', async ({ page }) => {
    await insertSegments(page, 2)
    const status = readout(page)

    // Registration happens on mount, before anything sounds.
    await expect(status).toHaveAttribute('data-sources', /stitch-arrangement/)
    await expect(status).toHaveAttribute('data-source', '')

    await page.getByTestId('stitch-transport-toggle').click()
    await expect(status).toHaveAttribute('data-source-kind', 'stitch-arrangement')
    await expect(status).toHaveAttribute('data-source-label', 'Stitch arrangement')
    await expect(status).toHaveAttribute('data-duration-sec', /[1-9]/)

    // Position is reported while it plays...
    const first = Number(await status.getAttribute('data-position-sec'))
    await page.waitForTimeout(400)
    const second = Number(await status.getAttribute('data-position-sec'))
    expect(second).toBeGreaterThan(first)

    // ...and freezes with the position it stopped at, not at zero.
    await page.getByTestId('stitch-transport-toggle').click()
    await expect(status).toHaveAttribute('data-source', '')
    const stopped = await status.getAttribute('data-position-sec')
    expect(Number(stopped)).toBeGreaterThan(0)
    await page.waitForTimeout(300)
    await expect(status).toHaveAttribute('data-position-sec', stopped)
  })

  test('the Speak deck and the Voice Edit A/B lane each report themselves as the active source', async ({ page }) => {
    const status = readout(page)

    await page.goto('/')
    await page.getByTestId('speak-text-input').fill('Transport coordinator.')
    await page.getByTestId('speak-generate-button').click()
    await expect(page.getByTestId('speak-result')).toBeVisible({ timeout: 30000 })
    // The deck autoplays its result, so it is the active source without a click.
    await expect(status).toHaveAttribute('data-source-kind', 'audio-deck')
    await expect(status).toHaveAttribute('data-source-label', 'Audio deck')

    await page.getByTestId('nav-voice-edit').click()
    await expect(page.getByTestId('voice-edit-page')).toBeVisible()
    await page.getByTestId('voice-edit-picker').selectOption({ index: 1 })
    const compare = page.getByTestId('alignment-compare')
    await expect(compare).toBeVisible()
    await compare.getByRole('button', { name: 'Original' }).click()
    await expect(status).toHaveAttribute('data-source-kind', 'voice-edit-ab')
    await expect(status).toHaveAttribute('data-source-label', 'Voice Edit A/B')
  })

  test('starting a snapshot audition pauses the arrangement through the coordinator', async ({ page }) => {
    await insertSegments(page, 2)
    const status = readout(page)

    await page.getByTestId('stitch-ab-capture-a').click()
    await page.getByTestId('stitch-transport-toggle').click()
    await expect(status).toHaveAttribute('data-source-kind', 'stitch-arrangement')
    await expect(page.getByTestId('stitch-transport-audio')).not.toHaveJSProperty('paused', true)

    await page.getByTestId('stitch-ab-audition-a').click()
    await expect(status).toHaveAttribute('data-source-kind', 'ab-snapshot')
    await expect(page.getByTestId('stitch-transport-audio')).toHaveJSProperty('paused', true)
  })

  test('starting playback never cancels a generation job', async ({ page }) => {
    // The always-on half of the job guarantee. With the default fake an async job is complete
    // the moment it is created, so this cannot hold one open -- the next test does that under
    // TEST_PROFILE=slow_async. What it guards is the coupling, which is the actual failure
    // mode: a coordinator that cancelled or paused jobs when audio started would issue
    // /generate/cancel or leave the job unfinished.
    //
    // Playback is started and asserted *before* the second job, deliberately: a new take swaps
    // the deck's src, which pauses it, so a readout assertion taken after that would be racing
    // the app's own legitimate pause rather than testing the coordinator.
    const cancels = []
    page.on('request', (request) => {
      if (request.url().includes('/generate/cancel')) cancels.push(request.url())
    })

    await page.goto('/')
    await page.getByTestId('speak-text-input').fill('Keep the job alive.')
    await page.getByTestId('speak-generate-button').click()
    await expect(page.getByTestId('speak-result')).toBeVisible({ timeout: 30000 })
    const firstTake = await page.getByTestId('speak-result').locator('audio').getAttribute('src')

    // Park the first take's deck paused, then start it by hand: audio is playing from here on.
    await page.getByTestId('speak-result').getByRole('button', { name: 'Pause audio' }).click()
    await page.getByTestId('speak-result').getByRole('button', { name: 'Play audio' }).click()
    await expect(readout(page)).toHaveAttribute('data-source-kind', 'audio-deck')

    // A second job starts while that playback is live, and still delivers its take.
    await page.getByTestId('speak-generate-button').click()
    await expect(page.getByTestId('speak-generate-button')).toBeEnabled({ timeout: 30000 })
    await expect(page.getByTestId('speak-error')).toHaveCount(0)
    await expect(page.getByTestId('speak-result').locator('audio')).not.toHaveAttribute('src', firstTake)
    expect(cancels).toEqual([])
  })

  test('a generation job outlives playback started while it runs', async ({ page }) => {
    // The overlap half, and the reason TEST_PROFILE=slow_async exists: with the default fake
    // the runtime completes an async job at creation (`async_jobs_complete_immediately`), so
    // there is no window to observe. The profile turns that off and slows the work to 3-5s
    // (tests/ui/fixtures/fake_model_server.py::_patch_generate_for_slow_async).
    //
    // Run it against a *fresh* server: the Playwright config reuses a running one locally, and
    // a server started without the profile makes the "still running" read below fail rather
    // than silently pass -- but a stale server is the first thing to check when it does.
    test.skip(PROFILE !== 'slow_async', 'needs TEST_PROFILE=slow_async: async jobs run 3-5s')

    const cancels = []
    page.on('request', (request) => {
      if (request.url().includes('/generate/cancel')) cancels.push(request.url())
    })

    await page.goto('/')
    await page.getByTestId('speak-text-input').fill('Keep the job alive.')
    await page.getByTestId('speak-generate-button').click()
    await expect(page.getByTestId('speak-result')).toBeVisible({ timeout: 30000 })

    // Park the first take's deck paused, so the click below is the thing that starts sounding.
    await page.getByTestId('speak-result').getByRole('button', { name: 'Pause audio' }).click()
    const playDeck = page.getByTestId('speak-result').getByRole('button', { name: 'Play audio' })
    await expect(playDeck).toBeVisible()
    const firstTake = await page.getByTestId('speak-result').locator('audio').getAttribute('src')

    // A second job, with the first take's deck still mounted and playable.
    await page.getByTestId('speak-generate-button').click()
    await expect(page.getByTestId('speak-generate-button')).toBeDisabled()
    await playDeck.click()

    // Point-in-time reads, not retrying assertions: "still running" has to be true at the
    // moment playback starts, and a retrying expect would happily wait for the job to finish
    // and then report that it had.
    expect(await page.getByTestId('speak-generate-button').isDisabled()).toBe(true)
    await expect(readout(page)).toHaveAttribute('data-source-kind', 'audio-deck')

    // The job then finishes on its own and hands over a new take.
    await expect(page.getByTestId('speak-generate-button')).toBeEnabled({ timeout: 30000 })
    await expect(page.getByTestId('speak-error')).toHaveCount(0)
    await expect(page.getByTestId('speak-result').locator('audio')).not.toHaveAttribute('src', firstTake)
    expect(cancels).toEqual([])
  })
})
