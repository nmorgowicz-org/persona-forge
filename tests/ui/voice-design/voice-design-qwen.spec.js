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
    await expect(page.getByTestId('voice-design-result')).toBeVisible({ timeout: 30000 })

    // Save to library
    const saveBtn = page.getByRole('button', { name: /save to library/i }).first()
    await expect(saveBtn).toBeVisible({ timeout: 5000 })
    await saveBtn.click()

    // Confirm the save confirmation appears and capture the saved voice id
    const savedLine = page.getByText(/saved as/i)
    await expect(savedLine).toBeVisible({ timeout: 15000 })
    const savedVoiceId = (await savedLine.innerText()).replace(/^saved as\s+/i, '').trim()

    // Navigate to Voice Library and confirm the saved voice card is present.
    // The fake server seeds committed fixture voices, so assert on the specific
    // card rather than an absolute total count.
    await page.getByTestId('nav-voice-library').click()
    const savedCard = page.locator('[data-testid="voice-card"]', { hasText: savedVoiceId })
    await expect(savedCard).toBeVisible({ timeout: 20000 })
  })

})
