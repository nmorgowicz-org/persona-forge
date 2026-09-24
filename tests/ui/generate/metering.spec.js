import { test, expect } from '@playwright/test'
import { pulsedWav, sineWav } from '../fixtures/signalFixtures.mjs'
import { generateWith, playAudio } from '../fixtures/speak.mjs'

// B-P4: truthful metering and one transport strip (audit A1 -- the "LEVEL" readout was a
// normalized peak bucket rendered as a percentage, which is not a level; and A2 -- it stepped
// with `timeupdate`).
//
// Every claim here is about the *number on screen being true*, so the fixtures carry known
// levels: a sine at -6 dBFS peak must read -6.0, and a 997 Hz sine at -20 dBFS peak must read
// -23.0 LUFS by BS.1770-4 (its mean square is -3.01 dB, and K-weighting at 997 Hz cancels the
// standard's -0.691 offset).
//
// RED-first: all five must fail on unmodified code.

// Generating, routing the result audio and starting playback all live in `fixtures/speak.mjs`,
// shared with the stitch specs that also make claims about a *playing* deck.

test.describe('B-P4: truthful metering and the transport strip', () => {
  test('a -6 dBFS peak reads -6.0 on the peak readout', async ({ page }) => {
    await generateWith(page, sineWav({ hz: 440, dbfs: -6, seconds: 2 }))
    await expect(page.getByTestId('deck-peak-readout')).toHaveText(/-6\.0/, { timeout: 20000 })
  })

  test('a 997 Hz sine at -20 dBFS peak reads -23.0 LUFS', async ({ page }) => {
    await generateWith(page, sineWav({ hz: 997, dbfs: -20, seconds: 2 }))
    await expect(page.getByTestId('deck-lufs-readout')).toHaveText(/-23\.0/, { timeout: 20000 })
  })

  test('a full-scale sample latches the clip LED, and clicking it clears', async ({ page }) => {
    // A full-scale *tone* rather than a one-sample impulse: the browser resamples into its own
    // AudioContext rate, which spreads a single sample (measured: -0.9 dBFS instead of 0). A
    // tone at 0 dBFS contains full-scale samples and arrives intact.
    await generateWith(page, sineWav({ hz: 997, dbfs: 0, seconds: 1 }))
    const led = page.getByTestId('deck-clip-led')
    await expect(led).toHaveAttribute('data-state', 'on', { timeout: 20000 })
    await led.click()
    await expect(led).toHaveAttribute('data-state', 'off')
  })

  test('the meter reports a live level that changes while playing', async ({ page }) => {
    // A steady tone cannot move a meter: any ballistic meter settles on a constant level and
    // every sample reads the same. The fixture alternates loud and quiet every 250 ms.
    await generateWith(page, pulsedWav({ hz: 440, loudDbfs: -6, quietDbfs: -40, seconds: 2 }))

    await playAudio(page)
    await page.waitForTimeout(300)

    const samples = await page.evaluate(async () => {
      const meter = document.querySelector('[role="meter"]')
      if (!meter) return null
      const read = () => Number(meter.getAttribute('aria-valuenow'))
      const out = []
      for (let i = 0; i < 10; i++) {
        out.push(read())
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
      }
      return out
    })
    expect(samples, 'no meter on the page').not.toBeNull()
    const moved = samples.slice(1).filter((value, i) => value !== samples[i]).length
    expect(moved, `levels: ${samples.join(', ')}`).toBeGreaterThan(0)
    // ...and it is a level, not a percentage: a -6 dBFS peak cannot sit at the top of a -60..0
    // scale, and a percentage readout would have no way to be negative.
    expect(Math.max(...samples)).toBeLessThan(0)
  })

  test('every deck instance uses the same transport strip with real hit targets', async ({ page }) => {
    const checkStrip = async (label) => {
      const strip = page.getByTestId('transport-strip').first()
      await expect(strip, `${label}: no transport strip`).toBeVisible({ timeout: 20000 })
      for (const name of [/^(Play|Pause) audio$/, 'Restart audio', 'Toggle loop']) {
        const button = strip.getByRole('button', { name }).first()
        await expect(button, `${label}: missing ${name}`).toBeVisible()
        const box = await button.boundingBox()
        expect(box, `${label}: ${name} has no box`).not.toBeNull()
        expect(Math.min(box.width, box.height), `${label}: ${name} is ${box.width}x${box.height}`).toBeGreaterThanOrEqual(32)
      }
    }

    // 1. Speak result
    await generateWith(page, sineWav({ hz: 440, dbfs: -12, seconds: 2 }))
    await checkStrip('Speak result')

    // 2. Voice Design result (Qwen) -- and save it, because the library row below needs a voice
    // to exist before there is a row to check.
    await page.getByTestId('nav-voice-design').click()
    await page.getByTestId('engine-qwen').click()
    await page.getByTestId('voice-design-description').fill('Warm, calm narrator.')
    await page.getByTestId('voice-design-sample-text').fill('This is a short sample line.')
    await page.getByTestId('voice-design-generate-button').click()
    await expect(page.getByTestId('voice-design-result')).toBeVisible({ timeout: 30000 })
    await checkStrip('Voice Design result')
    await page.getByRole('button', { name: /save to library/i }).first().click()

    // 3. Voice Library segment row (MiniAudioDeck) -- the library's own deck lives in the
    // Segments tab, where each row can audition itself.
    await page.getByTestId('nav-voice-library').click()
    await page.getByTestId('voice-library-tab-segments').click()
    await expect(page.getByTestId('transport-strip').first()).toBeVisible({ timeout: 20000 })
    await checkStrip('Voice Library segment row')

    // 4. OmniVoice candidate take (ClipPlayer)
    await page.getByTestId('nav-voice-design').click()
    await page.getByTestId('engine-omnivoice').click()
    await page.getByTestId('accent-bank-au').click()
    await page.getByTestId('omnivoice-script').fill('The quick brown fox jumps over the lazy dog.')
    await page.getByTestId('omnivoice-audition-button').click()
    await expect(page.getByTestId('omnivoice-candidate-take').nth(2)).toBeVisible({ timeout: 30000 })
    await checkStrip('OmniVoice candidate')
  })
})
