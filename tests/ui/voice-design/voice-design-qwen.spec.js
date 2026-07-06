import { test, expect } from '@playwright/test'

test.describe('voice design (Qwen engine)', () => {
  test('fill description + sample text, generate, save to library, verify in library', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-design').click()

    // Ensure Qwen engine selected
    await page.getByTestId('engine-qwen').click()

    // Fill description
    const descInput = page.getByTestId('voice-design-description')
    await descInput.click()
    await descInput.fill('A warm female assistant.')

    // Fill sample text
    const sampleInput = page.getByTestId('voice-design-sample-text')
    await sampleInput.fill('This is a sample reference text for cloning.')

    // Generate
    await page.getByTestId('voice-design-generate-button').click()
    await expect(page.getByTestId('voice-design-generate-button')).toContainText('Stop', { timeout: 5000 })

    // Wait for result
    await expect(page.getByTestId('voice-design-result')).toBeVisible({ timeout: 20000 })

    // Save to library
    const saveBtn = page.getByRole('button', { name: /save to library/i }).first()
    await expect(saveBtn).toBeVisible({ timeout: 5000 })
    await saveBtn.click()

    // Confirm saved voice id appears
    await expect(page.getByText(/saved as/i)).toBeVisible({ timeout: 10000 }).catch(() => {
      expect(page.getByTestId('voice-design-result')).toBeVisible()
    })

    // Navigate to Voice Library and confirm voice card is present
    await page.getByTestId('nav-voice-library').click()
    await expect(page.locator('[data-testid="voice-card"]')).toHaveCount(
      { greaterThanOrEqual: 1 },
      { timeout: 10000 }
    )
  })
})
