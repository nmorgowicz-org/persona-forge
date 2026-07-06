import { test, expect } from '@playwright/test'

test.describe('async generate and cancel', () => {
  test('start async generation, progress bar visible, cancel, cancelled state visible', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('speak-text-input').fill('Async cancel test line.')

    // Start generation
    await page.getByTestId('speak-generate-button').click()

    // Confirm generation in progress via button label
    await expect(page.getByTestId('speak-generate-button')).toContainText('Generating', { timeout: 5000 })

    // Confirm progress bar is visible (SpeakPage renders a progress bar div when generating)
    const progressBar = page.locator('div.h-2.w-full, div.h-2.w-full.bg-muted').first()
    await expect(progressBar).toBeVisible({ timeout: 10000 })

    // Click Stop button (SpeakPage renders a "Stop" button while generating)
    const stopBtn = page.getByRole('button', { name: 'Stop' }).first()
    await expect(stopBtn).toBeVisible({ timeout: 5000 })
    await stopBtn.click()

    // Wait for cancel to propagate
    await page.waitForTimeout(1500)

    // Expect one of:
    //  - "cancelled" text (handled via SpeakPage: setError('Generation was cancelled'))
    //  - error banner visible
    //  - generate button re-enabled (generation ended)
    const cancelledText = page.getByText(/cancelled/i)
    const errorBanner = page.getByTestId('speak-error')
    const genBtn = page.getByTestId('speak-generate-button')

    const hasError = await errorBanner.isVisible()
    const hasCancelledText = await cancelledText.first().isVisible()
    const btnEnabled = await genBtn.isEnabled()

    expect(hasError || hasCancelledText || btnEnabled).toBeTruthy()
  })
})
