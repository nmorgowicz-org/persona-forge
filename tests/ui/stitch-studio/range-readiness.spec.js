import { test, expect } from '@playwright/test'

// Fix for the defect found while writing A-4's specs: the per-clip "listen to just this
// segment" button was enabled as soon as the clip had source audio, which is *before* the
// shared transport had an audio element (and before the clip's own duration was known). A
// click in that window did nothing at all -- the transport's playRange has no element to
// play -- or, with an unknown duration, started a range of a few milliseconds.
//
// RED-first: on the unmodified code the button is enabled while the transport is not ready,
// so test 1 fails on the invariant and test 2 fails because the click produces no playback.

async function insertSegments(page, n) {
  await page.goto('/')
  await page.getByTestId('nav-stitch-studio').click()
  await page.getByTestId('stitch-picker-toggle-segments').click()
  const items = page.getByTestId('stitch-picker-item-segments')
  await expect(items.first()).toBeVisible()
  for (let i = 0; i < n; i++) await items.nth(i).click()
  await page.getByTestId('stitch-picker-insert-segments').click()
  await expect(page.getByTestId('stitch-clip')).toHaveCount(n)
}

const rangeButtonState = (page) =>
  page.evaluate(() => {
    const clip = document.querySelector('[data-testid="stitch-clip"]')
    const button = clip?.querySelector('[aria-label="Play clip playback"], [aria-label="Pause clip playback"]')
    const audio = document.querySelector('[data-testid="stitch-transport-audio"]')
    return {
      exists: !!button,
      enabled: button ? !button.disabled : null,
      audioAttached: !!audio,
      audioDuration: audio && Number.isFinite(audio.duration) ? Number(audio.duration.toFixed(3)) : null,
    }
  })

test.describe('per-clip range playback readiness', () => {
  test('the range button is never enabled before the transport can actually play', async ({ page }) => {
    await insertSegments(page, 2)
    const violations = []
    for (let i = 0; i < 40; i++) {
      const state = await rangeButtonState(page)
      if (state.enabled === true && (!state.audioAttached || !(state.audioDuration > 0))) {
        violations.push({ sample: i, ...state })
      }
      if (state.enabled === true && state.audioAttached && state.audioDuration > 0) break
      await page.waitForTimeout(50)
    }
    // An enabled button that cannot play is the bug: it silently swallows the click.
    expect(violations).toEqual([])
  })

  test('clicking it as soon as it is enabled plays the clip, not a degenerate span', async ({ page }) => {
    await insertSegments(page, 2)
    const card = page.getByTestId('stitch-clip').first()
    const button = card.locator('[aria-label="Play clip playback"], [aria-label="Pause clip playback"]')
    await expect(button).toBeEnabled({ timeout: 30000 })
    await button.click()

    const audio = page.getByTestId('stitch-transport-audio')
    // The range must actually run: a no-op click or a few-millisecond range fails here.
    await expect.poll(() => audio.evaluate((el) => el.currentTime), { timeout: 4000 }).toBeGreaterThan(0.5)
    const state = await audio.evaluate((el) => ({ paused: el.paused, duration: el.duration }))
    expect(state.paused).toBe(false)
    expect(state.duration).toBeGreaterThan(1)
  })
})
