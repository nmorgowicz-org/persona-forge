import { test, expect } from '@playwright/test'

test.describe('voice design', () => {
  test('describing and generating a voice saves it to the library', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-design').click()
    // OmniVoice is the default engine; this flow exercises the Qwen VoiceDesign panel.
    await page.getByTestId('engine-qwen').click()

    await page.getByTestId('voice-design-description').fill('Warm, calm narrator with a slight British accent.')
    await page.getByTestId('voice-design-sample-text').fill('This is a short sample line for the voice.')
    await page.getByTestId('voice-design-generate-button').click()

    await expect(page.getByTestId('voice-design-result')).toBeVisible({ timeout: 30000 })

    await page.getByRole('button', { name: /save to library/i }).first().click()

    await page.getByTestId('nav-voice-library').click()
    await expect(page.getByTestId('voice-card').first()).toBeVisible({ timeout: 20000 })
  })


  test('generate button is disabled until both description and sample text are set', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-design').click()
    await page.getByTestId('engine-qwen').click()
    await expect(page.getByTestId('voice-design-generate-button')).toBeDisabled()
  })

  test('OmniVoice is the default engine on a Qwen backend', async ({ page }) => {
    // The design engine is a voice-design concern, not a serving-backend one: pocket-tts
    // stays the default for cloning/serving, while voice design always opens on OmniVoice
    // (the only accent-capable engine). A Qwen backend must not pull the default back to
    // Qwen VoiceDesign.
    await page.route('**/health', async (route) => {
      const response = await route.fetch()
      const body = await response.json()
      await route.fulfill({
        response,
        json: { ...body, backend: 'pytorch', resolved_backend: 'pytorch' },
      })
    })
    await page.goto('/')
    await page.getByTestId('nav-voice-design').click()
    await expect(page.getByTestId('omnivoice-instruct')).toBeVisible({ timeout: 15000 })
    await expect(page.getByTestId('voice-design-description')).toHaveCount(0)
  })

  test('stitched preview is discarded when a take changes so Save cannot persist an unauditioned plan', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-design').click()
    await page.getByTestId('engine-omnivoice').click()
    await page.getByTestId('accent-bank-au').click()
    await page.getByTestId('omnivoice-script').fill('The quick brown fox jumps over the lazy dog.')
    await page.getByTestId('omnivoice-audition-button').click()

    const takes = page.getByTestId('omnivoice-candidate-take')
    await expect(takes.nth(2)).toBeVisible({ timeout: 30000 })

    await page.getByTestId('omnivoice-stitch-button').click()
    await expect(page.getByTestId('omnivoice-result')).toBeVisible({ timeout: 30000 })
    await expect(page.getByTestId('omnivoice-save-button')).toBeVisible()

    // Save persists the plan built from the current rack, so switching takes must discard the
    // preview (and its Save control) rather than leaving a render of the previous selection
    // next to a Save button that would persist a different one.
    await takes.nth(1).getByRole('button', { name: 'T2' }).click()
    await expect(page.getByTestId('omnivoice-result')).toHaveCount(0)
    await expect(page.getByTestId('omnivoice-save-button')).toHaveCount(0)

    // The invalidation is a reset, not a dead end: re-stitching the new selection works.
    await page.getByTestId('omnivoice-stitch-button').click()
    await expect(page.getByTestId('omnivoice-result')).toBeVisible({ timeout: 30000 })
  })
})
