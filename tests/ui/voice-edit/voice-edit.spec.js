import { test, expect } from '@playwright/test'

async function openVoiceEdit(page) {
  await page.goto('/')
  await page.getByTestId('nav-voice-edit').click()
  await expect(page.getByTestId('voice-edit-page')).toBeVisible()
}

test.describe('Voice Edit workspace', () => {
  test('Voice Edit deep link preselects the saved voice', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()
    await page.getByTestId('stitch-picker-toggle-segments').click()
    await page.getByTestId('stitch-picker-item-segments').nth(0).click()
    await page.getByTestId('stitch-picker-item-segments').nth(1).click()
    await page.getByTestId('stitch-picker-item-segments').nth(2).click()
    await page.getByTestId('stitch-picker-insert-segments').click()
    await page.getByTestId('stitch-voice-name').fill('Voice Edit deep link')
    await page.getByTestId('stitch-save-voice').click()
    await expect(page.getByTestId('stitch-adjust-prosody')).toBeVisible()
    const savedVoiceId = await page.getByTestId('stitch-adjust-prosody').evaluate((button) =>
      button.parentElement?.innerText.match(/(?:fake_voice_\d+|vd_[a-f0-9]+)/)?.[0] ?? '',
    )
    await page.getByTestId('stitch-adjust-prosody').click()

    await expect(page.getByTestId('voice-edit-page')).toBeVisible()
    await expect(page.getByTestId('voice-edit-picker')).toHaveValue(savedVoiceId)
  })

  test('variant saved in Voice Edit appears in Voice Library prosody editor', async ({ page }) => {
    await openVoiceEdit(page)
    await page.getByTestId('voice-edit-picker').selectOption({ index: 1 })
    await page.getByTestId('voice-edit-save-variant').click()
    await expect(page.getByTestId('voice-edit-variant')).toHaveCount(2, { timeout: 20000 })

    await page.getByTestId('nav-voice-library').click()
    await expect(page.getByTestId('voice-card').first()).toContainText('Prosody Variants')
    await expect(page.getByTestId('voice-card').first().getByText('Neutral variant')).toBeVisible()
  })

  test('Voice Library retains its existing prosody controls', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-library').click()
    await expect(page.getByTestId('voice-card').first().getByRole('button', { name: /Adjust prosody/i })).toBeVisible()
  })
})
