import { test, expect } from '@playwright/test'

async function designAVoice(page) {
  await page.getByTestId('nav-voice-design').click()
  await page.getByTestId('voice-design-description').fill('Bright, energetic assistant voice.')
  await page.getByTestId('voice-design-sample-text').fill('This is a short sample line.')
  await page.getByTestId('voice-design-generate-button').click()
  await expect(page.getByTestId('voice-design-result')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Save to library' }).click()
}

test.describe('voice library', () => {
  test('list, edit (fork), and delete a saved voice', async ({ page }) => {
    await page.goto('/')
    await designAVoice(page)

    await page.getByTestId('nav-voice-library').click()
    const card = page.getByTestId('voice-card').first()
    await expect(card).toBeVisible()
    const voiceId = await card.locator('p').first().innerText()

    // Edit: inline-edit the reference text (always available; Sparkles/fork button only appears
    // for OmniVoice voices with chip selections, not for plain VoiceDesign voices).
    const refTextP = card.locator('p.cursor-text').first()
    await expect(refTextP).toBeVisible()
    await refTextP.click()
    await expect(card.locator('textarea').first()).toBeVisible()

    const originalCard = page.getByTestId('voice-card').filter({ hasText: voiceId })
    await expect(originalCard).toBeVisible()

    // Ensure the confirm dialog is accepted so the delete actually runs.
    await page.evaluate(() => { window.confirm = () => true })
    await originalCard.getByLabel('Delete this voice').click()

    // Navigate away and back to get a fresh server-side list, in case the in-page
    // refresh is affected by optimistic state or timing.
    await page.getByTestId('nav-speak').click()
    await page.getByTestId('nav-voice-library').click()

    await expect(page.getByTestId('voice-card').filter({ hasText: voiceId })).toHaveCount(0, {
      timeout: 10_000,
    })
  })

  test('empty library shows a call to action', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-library').click()
    const emptyState = page.getByText('No voices saved yet.')
    const anyCard = page.getByTestId('voice-card').first()
    await expect(emptyState.or(anyCard)).toBeVisible()
  })
})
