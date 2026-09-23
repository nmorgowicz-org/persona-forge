import { test, expect } from '@playwright/test'

// A-4 (N6): exclusive audition -- one sound at a time. RED-first: on unmodified code every
// deck owns its own <audio> element with no coordination, so a second deck starting leaves
// the first one sounding. Plan: docs/plans/20260922-premium_audio_plugin_ux.md N6; runbook
// card A-4.
//
// The Voice Library's Segments tab is the one surface with several independent decks on a
// single page (each saved segment row carries its own deck), which is what makes the
// cross-owner case observable without navigating between pages.
//
// Two things keep these assertions from passing vacuously:
//   - Element handles are captured once, so a re-resolving locator can never follow a
//     different row and make an assertion meaningless.
//   - "Stopped" is asserted as *stopped mid-audio* (still time left on its own timeline),
//     within a bounded window. A deck that simply played to its end is not exclusive
//     audition, and the seeded rows are 2.6-2.9 s long, so a 700 ms window cannot be
//     satisfied by natural playback.

async function openSegmentAuditions(page) {
  await page.goto('/')
  await page.getByTestId('nav-voice-library').click()
  await page.getByRole('tab', { name: /^Segments$/ }).click()
  await expect(page.getByTestId('deck-waveform').first()).toBeVisible({ timeout: 15000 })
  // The innermost card around each deck: the outer list wrapper also contains audio
  // elements, so `:not(:has(section))` picks the per-row card only.
  const rows = page.locator('section:has(audio):not(:has(section))')
  await expect(rows.first()).toBeVisible()
  expect(await rows.count()).toBeGreaterThanOrEqual(3)

  const deck = async (i) => ({
    audio: await rows.nth(i).locator('audio').elementHandle(),
    toggle: rows.nth(i).locator('button[aria-label="Play audio"], button[aria-label="Pause audio"]'),
  })
  return { a: await deck(0), b: await deck(2), c: await deck(1) }
}

const state = (handle) => handle.evaluate((el) => ({ paused: el.paused, t: el.currentTime, d: el.duration }))

/** Stopped with audio still on its own timeline: the only way to be here is someone else
 * taking playback focus. */
async function expectStoppedMidAudio(handle, label) {
  await expect.poll(async () => (await state(handle)).paused, { timeout: 700, message: `${label} should be paused` }).toBe(true)
  const { t, d } = await state(handle)
  expect(t, `${label} stopped with ${(d - t).toFixed(2)}s of its own audio left`).toBeLessThan(d - 0.5)
}

test.describe('A-4: exclusive audition', () => {
  test('starting a second deck stops the first mid-audio', async ({ page }) => {
    const { a, b } = await openSegmentAuditions(page)

    await a.toggle.click()
    await expect.poll(async () => (await state(a.audio)).paused).toBe(false)
    await expect.poll(async () => (await state(b.audio)).paused).toBe(true)

    // Starting the second deck takes playback focus: the first must stop sounding.
    await b.toggle.click()
    await expect.poll(async () => (await state(b.audio)).paused).toBe(false)
    await expectStoppedMidAudio(a.audio, 'the first deck')

    // ... and focus moves back the other way, so it is a claim, not a one-way mute.
    await a.toggle.click()
    await expect.poll(async () => (await state(a.audio)).paused).toBe(false)
    await expectStoppedMidAudio(b.audio, 'the second deck')
  })

  test('a deck stopped by hand holds no focus, and the next deck still takes it', async ({ page }) => {
    const { a, b, c } = await openSegmentAuditions(page)

    await a.toggle.click()
    await expect.poll(async () => (await state(a.audio)).paused).toBe(false)
    await a.toggle.click()
    await expect.poll(async () => (await state(a.audio)).paused).toBe(true)

    // A deck that stopped on its own no longer holds focus, so the next one plays undisturbed.
    await b.toggle.click()
    await expect.poll(async () => (await state(b.audio)).paused).toBe(false)
    await page.waitForTimeout(400)
    expect((await state(b.audio)).paused).toBe(false)
    expect((await state(a.audio)).paused).toBe(true)

    // A third deck takes focus from the second, and the hand-stopped one stays stopped.
    await c.toggle.click()
    await expect.poll(async () => (await state(c.audio)).paused).toBe(false)
    await expectStoppedMidAudio(b.audio, 'the second deck')
    expect((await state(a.audio)).paused).toBe(true)
  })
})
