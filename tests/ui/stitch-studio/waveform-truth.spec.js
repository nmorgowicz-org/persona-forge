import { test, expect } from '@playwright/test'
import { sineWav } from '../fixtures/signalFixtures.mjs'
import { collectLongTasks } from '../fixtures/longtasks.mjs'
import { generateWith, playAudio } from '../fixtures/speak.mjs'

// B-P2: one true-scale hi-res waveform renderer.
//
// The three claims worth testing are all about honesty of the drawn signal, not about the
// renderer's internals: level is visible (a quieter clip draws shorter), motion is at display
// rate (not the browser's ~4 Hz `timeupdate`), and nothing renders as audio data before the
// audio exists.
//
// RED-first: tests 1, 2 and 4 must fail on unmodified code because the feature is missing.
// Test 3 is a *budget guard* rather than a feature test -- a performance budget cannot fail
// before the change that introduces the workload exists, so it is expected to pass both
// before and after; it is here to catch a regression the new renderer could introduce, and it
// reports whether the browser supports `longtask` at all rather than passing vacuously.

const LOUD_DBFS = -6
const QUIET_DBFS = -24

async function openStudio(page) {
  await page.goto('/')
  await page.getByTestId('nav-stitch-studio').click()
}

/** Serve generated tones as the segment library's audio, in order: loud, then quiet. */
async function routeSegmentAudio(page, { delayMs = 0 } = {}) {
  const loud = sineWav({ hz: 220, dbfs: LOUD_DBFS, seconds: 2 })
  const quiet = sineWav({ hz: 220, dbfs: QUIET_DBFS, seconds: 2 })
  let served = 0
  await page.route('**/omnivoice/segments/*/audio', async (route) => {
    const body = served++ === 0 ? loud : quiet
    if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs))
    await route.fulfill({ status: 200, contentType: 'audio/wav', body })
  })
}

async function insertSegments(page, n) {
  await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
  const items = page.getByTestId('stitch-picker-item-segments')
  await expect(items.first()).toBeVisible()
  for (let i = 0; i < n; i++) await items.nth(i).click()
  await page.getByTestId('stitch-picker-insert-segments').click()
  await expect(page.getByTestId('stitch-clip')).toHaveCount(n)
}

/** Tallest drawn column, in device pixels, for each canvas matching the selector. */
async function drawnHeights(page, selector) {
  return page.evaluate((sel) => {
    return [...document.querySelectorAll(sel)].map((canvas) => {
      const ctx = canvas.getContext('2d')
      const { width, height } = canvas
      if (!ctx || width === 0 || height === 0) return 0
      const { data } = ctx.getImageData(0, 0, width, height)
      let tallest = 0
      for (let x = 0; x < width; x++) {
        let count = 0
        for (let y = 0; y < height; y++) {
          if (data[(y * width + x) * 4 + 3] > 8) count++
        }
        if (count > tallest) tallest = count
      }
      return tallest
    })
  }, selector)
}

test.describe('B-P2: true-scale waveform renderer', () => {
  test('a quieter clip draws shorter than a louder one on the timeline', async ({ page }) => {
    await routeSegmentAudio(page)
    await openStudio(page)
    await insertSegments(page, 2)

    // Wait for both lanes to have decoded and drawn.
    await expect
      .poll(async () => (await drawnHeights(page, '[data-testid="stitch-waveform-canvas"]')).filter((h) => h > 0).length, {
        timeout: 20000,
      })
      .toBe(2)

    const [loud, quiet] = await drawnHeights(page, '[data-testid="stitch-waveform-canvas"]')
    // -6 dBFS against -24 dBFS is a factor of 0.126 in amplitude. Normalizing each clip to its
    // own maximum (the old behaviour) draws them the same height, which is exactly the
    // loudness mismatch this renderer exists to show.
    expect(quiet, `loud=${loud}px quiet=${quiet}px`).toBeLessThan(loud * 0.25)
  })

  test('the playhead moves at display rate, not at the browser timeupdate rate', async ({ page }) => {
    // Routed result audio, and an unguarded Play: this test failed on CI reading eight zeros,
    // which looked like a sampling artefact and was really a click that never happened (the
    // result card was up at -inf dBFS while the fake model was still loading, so the guarded
    // `if (isVisible())` skipped it and the deck never started).
    await generateWith(page, sineWav({ hz: 440, dbfs: -12, seconds: 2 }), 'Display rate playhead.')
    await playAudio(page)

    // Playback is genuinely moving before anything is sampled, so a deck that never started
    // fails here saying so rather than downstream as a set of identical numbers.
    const playhead = page.getByTestId('waveform-canvas')
    await expect
      .poll(async () => Number(await playhead.getAttribute('data-playhead-pct')), { timeout: 10000 })
      .toBeGreaterThan(0)

    // Eight samples ~40 ms apart: a playhead fed by `timeupdate` (~4 Hz) cannot move between
    // *every* pair, while one drawn per animation frame must. Sampling one pair would pass on
    // a stepped playhead by luck.
    const samples = await page.evaluate(async () => {
      const canvas = document.querySelector('[data-testid="waveform-canvas"]')
      if (!canvas) return null
      const read = () => Number(canvas.getAttribute('data-playhead-pct'))
      const out = []
      for (let i = 0; i < 8; i++) {
        out.push(read())
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
      }
      return out
    })
    expect(samples, 'no waveform canvas with a playhead readout').not.toBeNull()
    expect(samples.every((value) => Number.isFinite(value))).toBe(true)
    const moved = samples.slice(1).filter((value, i) => value !== samples[i]).length
    expect(moved, `positions: ${samples.join(', ')}`).toBe(samples.length - 1)
  })

  test('stitch playback stays inside the long-task budget', async ({ page }) => {
    await routeSegmentAudio(page)
    await openStudio(page)
    await insertSegments(page, 2)
    await expect(page.getByTestId('stitch-transport-toggle')).toBeEnabled({ timeout: 20000 })

    const result = await collectLongTasks(page, async () => {
      await page.getByTestId('stitch-transport-toggle').click()
      await page.waitForTimeout(3000)
      await page.getByTestId('stitch-transport-toggle').click()
    })

    expect(result.supported, 'PerformanceObserver longtask is unavailable in this browser').toBe(true)
    expect(result.over, `long tasks: ${result.all.join(', ')} ms`).toEqual([])
  })

  test('loading shows a designed skeleton, never placeholder bars', async ({ page }) => {
    // Slow the *decode* rather than the fetch: the clip only exists once its audio has landed,
    // so delaying the fetch hides the window instead of widening it. A slow decode is real
    // (long clips), and it is the state this skeleton exists for.
    await page.addInitScript(() => {
      const original = AudioContext.prototype.decodeAudioData
      AudioContext.prototype.decodeAudioData = function (...args) {
        return new Promise((resolve, reject) => {
          setTimeout(() => original.apply(this, args).then(resolve, reject), 1200)
        })
      }
    })
    await routeSegmentAudio(page)
    await openStudio(page)
    await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
    await page.getByTestId('stitch-picker-item-segments').first().click()
    await page.getByTestId('stitch-picker-insert-segments').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)

    await expect(page.getByTestId('waveform-skeleton').first()).toBeVisible({ timeout: 5000 })
    // ...and it resolves into a real waveform rather than staying decorative.
    await expect(page.getByTestId('waveform-skeleton')).toHaveCount(0, { timeout: 20000 })
    await expect
      .poll(async () => (await drawnHeights(page, '[data-testid="stitch-waveform-canvas"]')).some((h) => h > 0), { timeout: 20000 })
      .toBe(true)
  })
})
