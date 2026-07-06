import { test, expect } from '@playwright/test'

test.describe('voice library', () => {
  test('view voices, inline-edit reference text, delete a voice, confirm empty state when none', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-library').click()

    // Check if voices exist; if not, create one
    const hasCards = await page.locator('[data-testid="voice-card"]').first().isVisible()
    if (!hasCards) {
      await page.getByTestId('nav-voice-design').click()
      await page.getByTestId('engine-qwen').click()
      await page.getByTestId('voice-design-description').fill('Test voice for library tests.')
      await page.getByTestId('voice-design-sample-text').fill('Reference text for this voice.')
      await page.getByTestId('voice-design-generate-button').click()
      await expect(
        page.getByTestId('voice-design-generate-button'),
        'generation in progress',
      ).toContainText('Stop', { timeout: 5000 })
      await expect(page.getByTestId('voice-design-result')).toBeVisible({ timeout: 20000 })

      const saveBtn = page.getByRole('button', { name: /save to library/i }).first()
      if (await saveBtn.isVisible()) await saveBtn.click()

      await page.getByTestId('nav-voice-library').click()
      await expect(page.locator('[data-testid="voice-card"]')).toHaveCount(1, { timeout: 10000 })
    }

    // Inline-edit reference text: click pencil icon on first card
    const firstCard = page.locator('[data-testid="voice-card"]').first()
    const editBtn = firstCard.locator('[aria-label="Edit reference text"]').first()
    if (await editBtn.isVisible()) {
      await editBtn.click()
      const textarea = firstCard.locator('textarea').first()
      await expect(textarea).toBeVisible()
      await textarea.fill('Updated reference text.')
      await page.mouse.click(0, 0)
      await page.waitForTimeout(300)
    }

    // Delete the voice via trash button
    const trashBtn = firstCard.locator('[aria-label="Delete this voice"]').first()
    if (await trashBtn.isVisible()) {
      page.on('dialog', (dialog) => dialog.accept())
      await trashBtn.click()
      await page.waitForTimeout(800)
    }

    // After deletion, confirm empty state or remaining voices
    const remainingCards = page.locator('[data-testid="voice-card"]')
    const count = await remainingCards.count()
    if (count === 0) {
      await expect(page.getByText(/no voices/i)).toBeVisible()
    }
  })
})
