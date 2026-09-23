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

// A-4b: the two remaining audio owners -- the segment browser's row audition and the
// prosody variant preview -- both play through media elements of their own (the preview's is
// never attached to the document at all), so "one sound at a time" is asserted as an
// owner-agnostic invariant: at most one media element is ever sounding. A script installed
// before the app loads records every element that has ever been asked to play.
async function trackMedia(page) {
  await page.addInitScript(() => {
    window.__media = []
    const originalPlay = HTMLMediaElement.prototype.play
    HTMLMediaElement.prototype.play = function (...args) {
      if (!window.__media.includes(this)) window.__media.push(this)
      return originalPlay.apply(this, args)
    }
  })
}

const playingCount = (page) => page.evaluate(() => (window.__media ?? []).filter((el) => !el.paused && !el.ended).length)

/** The arrangement preview is rendered more than once; a later render replaces the audio
 * element's src and resets playback to zero, which would silently invalidate any assertion
 * about the transport being stopped. Wait until the src and duration hold still. */
async function waitForSettledPreview(page) {
  const transport = page.getByTestId('stitch-transport-audio')
  await expect(page.getByTestId('stitch-preview-ready')).toBeVisible({ timeout: 30000 })
  await expect(transport).toHaveAttribute('src', /^blob:/)
  let previous = null
  for (let i = 0; i < 30; i++) {
    const now = await transport.evaluate((el) => ({ src: el.src, d: el.duration }))
    if (previous && previous.src === now.src && previous.d === now.d && Number.isFinite(now.d) && now.d > 1) return transport
    previous = now
    await page.waitForTimeout(250)
  }
  throw new Error('the preview never settled on a final render')
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

/** Establishes arrangement playback and returns the transport element's src, retrying if a
 * preview re-render resets it. Only the setup retries; the assertions stay strict. */
async function startArrangementPlaying(page, transport) {
  for (let attempt = 0; attempt < 6; attempt++) {
    await page.locator('body').click()
    await page.keyboard.press('Space')
    const src = await transport.evaluate((el) => el.src)
    try {
      await expect.poll(() => transport.evaluate((el) => el.currentTime), { timeout: 3000 }).toBeGreaterThan(0.4)
    } catch {
      continue
    }
    const now = await transport.evaluate((el) => ({ src: el.src, paused: el.paused }))
    if (now.src === src && !now.paused) return src
  }
  throw new Error('could not establish arrangement playback')
}

test.describe('A-4b: the last two audio owners', () => {
  test('auditioning a segment row stops the arrangement playing underneath', async ({ page }) => {
    await trackMedia(page)
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()
    await page.getByTestId('stitch-picker-toggle-segments').click()
    const items = page.getByTestId('stitch-picker-item-segments')
    await expect(items.first()).toBeVisible()
    for (let i = 0; i < 2; i++) await items.nth(i).click()
    await page.getByTestId('stitch-picker-insert-segments').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(2)

    const transport = await waitForSettledPreview(page)
    // The preview can re-render again later (the plan changes when a clip's analysis lands),
    // which resets the transport element to zero. That is a *setup* problem: retry until
    // playback is genuinely established, so the assertion below measures the audition.
    const srcBefore = await startArrangementPlaying(page, transport)

    // The browser opens over the playing arrangement; auditioning a row must take focus.
    await page.getByTestId('stitch-picker-toggle-segments').click()
    await expect(page.getByTestId('segment-browser-dialog')).toBeVisible()
    const audition = page.getByTestId('segment-browser-audio').first()
    await audition.click()
    await expect.poll(() => audition.getAttribute('data-playing')).toBe('true')

    await expect.poll(() => transport.evaluate((el) => el.paused), { timeout: 2000 }).toBe(true)
    const after = await transport.evaluate((el) => ({ src: el.src, t: el.currentTime }))
    expect(after.src, 'the preview was re-rendered, so this proves nothing').toBe(srcBefore)
    expect(after.t, 'the arrangement was reset to zero, not stopped mid-playback').toBeGreaterThan(0.4)
    expect(await playingCount(page)).toBe(1)
  })

  test('previewing a prosody variant stops when the lane compare starts', async ({ page }) => {
    await trackMedia(page)
    await page.goto('/')
    await page.getByTestId('nav-voice-edit').click()
    await expect(page.getByTestId('voice-edit-page')).toBeVisible()
    await page.getByTestId('voice-edit-picker').selectOption({ index: 1 })

    const preview = page.locator('[aria-label="Preview this variant"]').first()
    await expect(preview).toBeVisible({ timeout: 20000 })
    await preview.click()
    await expect.poll(() => playingCount(page), { timeout: 5000 }).toBe(1)

    // The compare's lane player is a different owner: starting it must silence the preview.
    const compare = page.getByTestId('alignment-compare').getByRole('button', { name: 'Original' })
    await expect(compare).toBeVisible({ timeout: 20000 })
    await compare.click()
    await expect.poll(() => playingCount(page), { timeout: 3000 }).toBe(1)
    // ... and the preview really did stop, rather than the compare never starting.
    expect(await page.locator('[aria-label="Preview this variant"], [aria-label="Stop preview"]').first().getAttribute('aria-label')).not.toBe('Stop preview')
  })
})
