import { expect } from '@playwright/test'

// Generating on the Speak page, with the result audio under the test's control.
//
// The result card appears as soon as the job is accepted, which is not the same moment as the
// audio existing: on a slow machine the card sits at `-inf dBFS` behind a "Model is still
// loading" chip until the backend is ready, and there is no play control to press yet. Routing
// the result bytes makes both the content and the timing ours, so a spec can press Play and mean
// it. Every claim about a *playing* deck belongs on this helper rather than on the fake model's
// startup latency.

export const SPEAK_RESULT_AUDIO = '**/generate/job/*/audio*'

/** Serve `body` (a WAV buffer from `signalFixtures.mjs`) as every generated result's audio. */
export async function routeSpeakResult(page, body) {
  await page.route(SPEAK_RESULT_AUDIO, (route) => route.fulfill({ status: 200, contentType: 'audio/wav', body }))
}

/** Open Speak, generate `text`, and leave the result card up with `body` as its audio. */
export async function generateWith(page, body, text = 'Metering fixture.') {
  await routeSpeakResult(page, body)
  await page.goto('/')
  await page.getByTestId('speak-text-input').fill(text)
  await page.getByTestId('speak-generate-button').click()
  await expect(page.getByTestId('speak-result')).toBeVisible({ timeout: 30000 })
}

/**
 * Ensure the Speak result is playing, or fail saying so.
 *
 * Two traps this exists to avoid, both hit for real:
 *
 * 1. The deck **auto-plays** when its audio arrives (`AudioDeck`'s `autoPlay` defaults true), so
 *    the control usually already reads "Pause audio" by the time a spec looks. A lookup for
 *    "Play audio" then matches nothing, and a guarded `if (await play.isVisible())` click skips
 *    silently -- leaving the spec to measure playback that merely happened to be running.
 * 2. Pressing whatever button is there is not the fix either: pressing "Pause audio" *stops* the
 *    very thing the caller came to measure.
 *
 * So: start it if it is not running, then assert that it is. A deck that never plays fails here,
 * saying so, instead of downstream as eight identical numbers.
 */
export async function playAudio(page) {
  const result = page.getByTestId('speak-result')
  const start = result.getByRole('button', { name: 'Play audio' })
  const pause = result.getByRole('button', { name: 'Pause audio' })

  // The result card appears before its audio does; wait for a transport that is actually usable.
  await expect(start.or(pause).first(), 'the Speak result has no usable transport').toBeEnabled({ timeout: 20000 })
  if (await start.isVisible()) await start.click()
  await expect(pause, 'the Speak result is not playing').toBeVisible({ timeout: 10000 })
}
