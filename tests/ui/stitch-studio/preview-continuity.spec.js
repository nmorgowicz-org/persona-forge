import { test, expect } from '@playwright/test'

// Fix for the preview churn that kept invalidating transport assertions across A-4/A-4b.
//
// Investigation: `hashStitchPlan` deliberately excludes fields that cannot change the audio
// (`durationMs`, text), so every re-render is a *real* plan change -- typically the
// punctuation gap suggestion landing ~1s after segments are inserted (paddingMs 0 -> 520),
// and analysis-driven edits later. The renders are correct; what is broken is that swapping
// the preview's src resets the transport: the element is emptied, playback stops, and the
// playhead jumps to zero. A DAW re-rendering a region does not stop the transport.
//
// RED-first: on unmodified code the swap stops playback and zeroes the position.

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

/** The preview is rendered more than once; wait for a render that holds still. */
async function waitForSettledPreview(page) {
  const transport = page.getByTestId('stitch-transport-audio')
  await expect(page.getByTestId('stitch-preview-ready')).toBeVisible({ timeout: 30000 })
  await expect(transport).toHaveAttribute('src', /^blob:/)
  let previous = null
  for (let i = 0; i < 40; i++) {
    const now = await transport.evaluate((el) => ({ src: el.src, d: el.duration }))
    if (previous && previous.src === now.src && previous.d === now.d && Number.isFinite(now.d) && now.d > 1) return transport
    previous = now
    await page.waitForTimeout(250)
  }
  throw new Error('the preview never settled')
}

/** Establishes arrangement playback, retrying if a render lands while starting. */
async function startPlaying(page, transport) {
  for (let attempt = 0; attempt < 6; attempt++) {
    await page.locator('body').click()
    await page.keyboard.press('Space')
    const src = await transport.evaluate((el) => el.src)
    try {
      await expect.poll(() => transport.evaluate((el) => el.currentTime), { timeout: 3000 }).toBeGreaterThan(0.5)
    } catch {
      continue
    }
    const now = await transport.evaluate((el) => ({ src: el.src, paused: el.paused, t: el.currentTime }))
    if (now.src === src && !now.paused) return { src, t: now.t }
  }
  throw new Error('could not establish playback')
}

test.describe('preview continuity', () => {
  test('a preview re-render does not stop or rewind playback', async ({ page }) => {
    await insertSegments(page, 2)
    const transport = await waitForSettledPreview(page)
    const { src: srcBefore, t: tBefore } = await startPlaying(page, transport)

    // Force a plan change that must re-render the preview: editing a seam changes paddingMs,
    // which the plan hash includes.
    const gap = page.getByTestId('stitch-gap-control').first()
    await gap.getByRole('button', { name: /Gap between clip/ }).click()
    const input = gap.getByRole('textbox')
    await input.fill('700')
    await input.press('Enter')

    // The preview really was re-rendered ...
    await expect.poll(() => transport.evaluate((el) => el.src), { timeout: 15000 }).not.toBe(srcBefore)

    // ... and the transport carried on instead of resetting to zero and stopping.
    const after = await transport.evaluate((el) => ({ paused: el.paused, t: el.currentTime, d: el.duration }))
    expect(after.paused, 'playback stopped when the preview was re-rendered').toBe(false)
    expect(after.t, 'the playhead was rewound by the re-render').toBeGreaterThan(tBefore * 0.5)
  })

  test('a preview re-render keeps the position of a paused transport', async ({ page }) => {
    await insertSegments(page, 2)
    const transport = await waitForSettledPreview(page)

    // Park the playhead at a known arrangement position, paused.
    const ruler = page.getByTestId('stitch-timeline-ruler')
    const box = await ruler.boundingBox()
    await page.mouse.click(box.x + box.width * 0.5, box.y + 8)
    const srcBefore = await transport.evaluate((el) => el.src)
    const parked = await transport.evaluate((el) => ({ t: el.currentTime, d: el.duration }))
    expect(parked.t).toBeGreaterThan(0.5)
    const fraction = parked.t / parked.d

    const gap = page.getByTestId('stitch-gap-control').first()
    await gap.getByRole('button', { name: /Gap between clip/ }).click()
    const input = gap.getByRole('textbox')
    await input.fill('650')
    await input.press('Enter')

    // Wait for the *replacement* render, not merely for a src to exist.
    await expect.poll(() => transport.evaluate((el) => el.src), { timeout: 15000 }).not.toBe(srcBefore)
    await expect
      .poll(async () => {
        const now = await transport.evaluate((el) => Number(el.duration))
        return Number.isFinite(now) && now > 1
      })
      .toBe(true)

    const after = await transport.evaluate((el) => ({ paused: el.paused, t: el.currentTime, d: el.duration }))
    expect(after.paused).toBe(true)
    // Same position in the arrangement, expressed as a fraction so a slightly longer or
    // shorter render cannot fail it.
    expect(Math.abs(after.t / after.d - fraction)).toBeLessThan(0.05)
  })
})
