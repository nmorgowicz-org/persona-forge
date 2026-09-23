import { test, expect } from '@playwright/test'

// A-4 (M1): the arrangement loop brace. RED-first: on unmodified code no brace exists at all
// (dragging the ruler only seeks), so every test here fails on the missing feature, then
// passes once the brace is implemented. The third test also carries the regression guard the
// card asks for -- a per-clip range play must still play only its clip, loop or no loop.
// Plan: docs/plans/20260922-premium_audio_plugin_ux.md M1; runbook card A-4.

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

// The arrangement preview is rendered more than once (a partial render can land first), and
// every transport calculation -- seek mapping, clip ranges, the loop's own seconds -- scales
// with the *final* duration. Wait until both the blob src and the duration hold still, or a
// range measured against a partial preview collapses to a fraction of a second.
async function readyPreview(page) {
  await expect(page.getByTestId('stitch-preview-ready')).toBeVisible({ timeout: 30000 })
  const audio = page.getByTestId('stitch-transport-audio')
  await expect(audio).toHaveAttribute('src', /^blob:/)
  let previous = null
  for (let i = 0; i < 30; i++) {
    const now = await audio.evaluate((el) => ({ src: el.src, d: el.duration }))
    // `d > 1` rejects a partial render (tens of milliseconds): one of those landing first
    // shrinks previewScale to a fraction of its real value, which collapses every clip range
    // and seek target the transport computes from it.
    if (previous && previous.src === now.src && previous.d === now.d && Number.isFinite(now.d) && now.d > 1) return audio
    previous = now
    await page.waitForTimeout(250)
  }
  throw new Error('the preview never settled on a final render')
}

// The ruler spans the whole lane (inset-y-0) but the clip row sits above it in the z-order
// (Reorder.Group is z-[1], the ruler z-0), so only the ruler's own top strip is actually
// hittable -- the same reason the existing seek test clicks at y + 8 rather than mid-lane.
async function dragOnRuler(page, fromFraction, toFraction) {
  const ruler = page.getByTestId('stitch-timeline-ruler')
  const box = await ruler.boundingBox()
  if (!box) throw new Error('ruler has no bounding box')
  const y = box.y + 8
  await page.mouse.move(box.x + box.width * fromFraction, y)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width * toFraction, y, { steps: 8 })
  await page.mouse.up()
  return box
}

const loopBounds = async (page) => {
  const brace = page.getByTestId('loop-brace')
  return {
    start: Number(await brace.getAttribute('data-loop-start')),
    end: Number(await brace.getAttribute('data-loop-end')),
  }
}

test.describe('A-4: arrangement loop brace', () => {
  test('dragging across the ruler creates a loop brace that Space wraps playback to', async ({ page }) => {
    await insertSegments(page, 2)
    const audio = await readyPreview(page)

    const box = await dragOnRuler(page, 0.15, 0.22)
    const brace = page.getByTestId('loop-brace')
    await expect(brace).toBeVisible()
    await expect(page.getByTestId('loop-brace-handle-start')).toBeVisible()
    await expect(page.getByTestId('loop-brace-handle-end')).toBeVisible()

    // The brace covers the dragged span, in seconds, on the ruler's own scale.
    const { start, end } = await loopBounds(page)
    expect(start).toBeGreaterThan(0)
    expect(end).toBeGreaterThan(start)
    const braceBox = await brace.boundingBox()
    expect(Math.abs(braceBox.x - (box.x + box.width * 0.15))).toBeLessThanOrEqual(4)
    expect(Math.abs(braceBox.width - box.width * 0.07)).toBeLessThanOrEqual(4)

    // Space plays the arrangement and wraps back to the brace start instead of running past
    // the brace end. Sampled from the shared transport's own audio element.
    await page.locator('body').click()
    const srcBefore = await audio.evaluate((el) => el.src)
    await page.keyboard.press('Space')
    await expect(page.getByTestId('stitch-transport-toggle')).toHaveAttribute('aria-label', 'Pause')

    const samples = []
    let wrappedAt = -1
    for (let i = 0; i < 40; i++) {
      samples.push(await audio.evaluate((el) => el.currentTime))
      if (i > 0 && samples[i] < samples[i - 1] - 0.05) {
        wrappedAt = i
        break
      }
      await page.waitForTimeout(30)
    }
    expect(wrappedAt, 'playback never wrapped back').toBeGreaterThan(0)
    // The wrap lands on the brace start. This is what separates a real loop from the element
    // simply resetting to zero, which is also a "decrease" in the samples.
    expect(samples[wrappedAt]).toBeGreaterThanOrEqual(start * 0.8)
    expect(samples[wrappedAt]).toBeLessThanOrEqual(end)
    // The preview can re-render mid-measurement (new blob src, element back to 0), which would
    // make the samples above meaningless -- so validate the detection rather than trust it.
    expect(await audio.evaluate((el) => el.src), 'the preview was re-rendered during measurement').toBe(srcBefore)

    // ... and after wrapping it stays inside the brace rather than running past its end.
    const after = []
    for (let i = 0; i < 10; i++) {
      after.push(await audio.evaluate((el) => el.currentTime))
      await page.waitForTimeout(30)
    }
    expect(Math.max(...after)).toBeLessThanOrEqual(end * 1.05 + 0.25)
    await page.keyboard.press('Space')
  })

  test('zooming keeps the brace on the same times', async ({ page }) => {
    await insertSegments(page, 2)
    await readyPreview(page)

    await dragOnRuler(page, 0.2, 0.4)
    const brace = page.getByTestId('loop-brace')
    await expect(brace).toBeVisible()
    const before = await loopBounds(page)
    const boxBefore = await brace.boundingBox()

    await page.getByTestId('stitch-zoom-in').click()
    await page.getByTestId('stitch-zoom-in').click()

    // Times are the source of truth (seconds), so zooming cannot move the loop ...
    const after = await loopBounds(page)
    expect(after.start).toBe(before.start)
    expect(after.end).toBe(before.end)
    // ... while the brace itself stretches with the timeline.
    const boxAfter = await brace.boundingBox()
    expect(boxAfter.width).toBeGreaterThan(boxBefore.width)
    await expect(brace).toBeVisible()
  })

  test('a clip range still plays only its clip while a loop is set', async ({ page }) => {
    await insertSegments(page, 2)
    const audio = await readyPreview(page)

    // A loop at the very start of the arrangement, far narrower than any clip's span: if
    // playback honoured the loop during a clip range, it would wrap forever and the range
    // would never reach its own end.
    await dragOnRuler(page, 0.005, 0.02)
    await expect(page.getByTestId('loop-brace')).toBeVisible()

    // Scoped to one clip's card: a page-wide "Play clip playback" locator would match the
    // *other* clip's idle button and let both assertions below pass instantly.
    const card = page.getByTestId('stitch-clip').first()
    const rangeButton = card.locator('[aria-label="Play clip playback"], [aria-label="Pause clip playback"]')
    await rangeButton.click()
    await expect(card.locator('[aria-label="Pause clip playback"]')).toBeVisible()

    // The range plays through and stops on its own end (its own button flips back), which is
    // only reachable if the loop did not hijack the clip's bounded playback -- the loop here
    // is a fraction of a second long, so a hijacked range would never finish.
    // Sampled while it plays: the loop must never pull the range back to its own start.
    const during = []
    for (let i = 0; i < 12; i++) {
      during.push(await audio.evaluate((el) => el.currentTime))
      if (await card.locator('[aria-label="Play clip playback"]').isVisible()) break
      await page.waitForTimeout(100)
    }
    expect(during.every((t, i) => i === 0 || t >= during[i - 1] - 0.02), 'the range was pulled back to the loop').toBe(true)

    await expect(card.locator('[aria-label="Play clip playback"]')).toBeVisible({ timeout: 15000 })
    const state = await audio.evaluate((el) => ({ paused: el.paused, currentTime: el.currentTime }))
    expect(state.paused).toBe(true)
    expect(state.currentTime).toBeGreaterThan(0)
    // Everything above is deliberately scale-free. The brace is a fraction of a second at the
    // arrangement's start while the clip spans seconds, so in the transport's own seconds the
    // range always outlives the loop -- which is why "it finished by itself" and "it never
    // went backwards" together prove the loop did not own this playback. Comparing raw values
    // across the two would be wrong: the loop is stored in arrangement seconds, the element
    // plays preview seconds, and previewScale can be stale (see readyPreview).
  })
})
