import { test, expect } from '@playwright/test'

test.describe('voice design', () => {
  test('describing and generating a voice saves it to the library', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-design').click()

    await page.getByTestId('voice-design-description').fill('Warm, calm narrator with a slight British accent.')
    await page.getByTestId('voice-design-sample-text').fill('This is a short sample line for the voice.')
    await page.getByTestId('voice-design-generate-button').click()

    await expect(page.getByTestId('voice-design-result')).toBeVisible({ timeout: 15_000 })

    await page.getByTestId('nav-voice-library').click()
    await expect(page.getByTestId('voice-card').first()).toBeVisible()
  })

  test('generate button is disabled until both description and sample text are set', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-design').click()
    await expect(page.getByTestId('voice-design-generate-button')).toBeDisabled()
  })
})
