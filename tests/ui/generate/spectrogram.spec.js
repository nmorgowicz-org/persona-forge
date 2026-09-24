import { test, expect } from '@playwright/test'
import { sineWav } from '../fixtures/signalFixtures.mjs'
import { collectLongTasks } from '../fixtures/longtasks.mjs'

// B-P3: the spectrogram view (audit A6 -- `SpectralAccent` re-drew the peak array as cells and
// invented a sine when it had nothing, so nothing on screen was ever spectral data).
//
// The claim worth testing is that the picture is *real*: a tone at a known frequency must land
// at the right place on a log-frequency axis. That is asserted from canvas pixels, not from the
// component's own bookkeeping.
//
// RED-first: tests 1 and 2 must fail on unmodified code because the feature is missing. Test 3
// is a *budget guard* like B-P2's: a performance budget cannot fail before the workload exists,
// so it is expected to pass on both sides and exists to catch the STFT creeping onto the main
// thread.

const TONE_HZ = 1000
const TONE_DBFS = -12
const F_MIN = 50
const F_MAX = 12000

/** The axis the renderer and this spec agree on: high frequencies at the top. */
const hzForRow = (y, height) => F_MIN * (F_MAX / F_MIN) ** (1 - y / (height - 1))

/** Serve a known tone as the Speak result's audio (the async job's own download). */
async function routeSpeakResult(page) {
  const tone = sineWav({ hz: TONE_HZ, dbfs: TONE_DBFS, seconds: 2 })
  await page.route('**/generate/job/*/audio*', (route) =>
    route.fulfill({ status: 200, contentType: 'audio/wav', body: tone }),
  )
}

async function generateTone(page) {
  await page.goto('/')
  await page.getByTestId('speak-text-input').fill('Spectrogram tone.')
  await page.getByTestId('speak-generate-button').click()
  await expect(page.getByTestId('speak-result')).toBeVisible({ timeout: 30000 })
}

test.describe('B-P3: spectrogram view', () => {
  test('a 1 kHz tone renders its band at 1 kHz on the log axis', async ({ page }) => {
    await routeSpeakResult(page)
    await generateTone(page)

    await page.getByTestId('view-spectrum').click()
    const canvas = page.getByTestId('spectrogram-canvas')
    await expect(canvas).toBeVisible({ timeout: 20000 })

    const read = await page.evaluate(async () => {
      const el = document.querySelector('[data-testid="spectrogram-canvas"]')
      if (!el) return null
      // Wait for the worker to land and the canvas to be painted.
      for (let i = 0; i < 60; i++) {
        const ctx = el.getContext('2d')
        const { data } = ctx.getImageData(Math.floor(el.width / 2), 0, 1, el.height)
        const brightest = Math.max(...Array.from({ length: el.height }, (_, y) => data[y * 4] + data[y * 4 + 1] + data[y * 4 + 2]))
        if (brightest > 60) break
        await new Promise((resolve) => setTimeout(resolve, 100))
      }
      const ctx = el.getContext('2d')
      const { data } = ctx.getImageData(Math.floor(el.width / 2), 0, 1, el.height)
      let bestY = 0
      let best = -1
      for (let y = 0; y < el.height; y++) {
        const luminance = data[y * 4] + data[y * 4 + 1] + data[y * 4 + 2]
        if (luminance > best) {
          best = luminance
          bestY = y
        }
      }
      return { height: el.height, width: el.width, bestY, best }
    })

    expect(read, 'no spectrogram canvas').not.toBeNull()
    const hz = hzForRow(read.bestY, read.height)
    // A twelfth of an octave is the resolution the axis can be read at; anything further off
    // means the frequency mapping is wrong, not that the FFT is imprecise.
    expect(hz, `brightest row ${read.bestY}/${read.height} -> ${hz.toFixed(0)} Hz`).toBeGreaterThan(TONE_HZ / 2 ** (1 / 12))
    expect(hz, `brightest row ${read.bestY}/${read.height} -> ${hz.toFixed(0)} Hz`).toBeLessThan(TONE_HZ * 2 ** (1 / 12))
  })

  test('the Wave/Spectrum choice survives navigating away and back', async ({ page }) => {
    await routeSpeakResult(page)
    await generateTone(page)

    await page.getByTestId('view-spectrum').click()
    await expect(page.getByTestId('spectrogram-canvas')).toBeVisible({ timeout: 20000 })

    await page.getByTestId('nav-stitch-studio').click()
    await expect(page.getByTestId('stitch-picker-toggle-segments')).toBeVisible({ timeout: 15000 })
    await page.getByTestId('nav-speak').click()
    await expect(page.getByTestId('speak-result')).toBeVisible({ timeout: 15000 })

    await expect(page.getByTestId('spectrogram-canvas')).toBeVisible({ timeout: 20000 })
  })

  test('the STFT stays off the main thread', async ({ page }) => {
    await routeSpeakResult(page)
    await generateTone(page)

    const result = await collectLongTasks(page, async () => {
      await page.getByTestId('view-spectrum').click()
      await expect(page.getByTestId('spectrogram-canvas')).toBeVisible({ timeout: 20000 })
      await page.waitForTimeout(1000)
    })

    expect(result.supported, 'PerformanceObserver longtask is unavailable in this browser').toBe(true)
    expect(result.over, `long tasks: ${result.all.join(', ')} ms`).toEqual([])
  })
})
