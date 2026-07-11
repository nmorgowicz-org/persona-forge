import { test, expect } from '@playwright/test'

async function ensureVoice(page) {
  await page.goto('/')
  if (!(await page.getByTestId('nav-voice-library').isVisible())) await page.getByRole('button', { name: 'Toggle Sidebar' }).click()
  await page.getByTestId('nav-voice-library').click()
  if (await page.locator('[data-testid="voice-card"]').count()) return
  if (!(await page.getByTestId('nav-voice-design').isVisible())) await page.getByRole('button', { name: 'Toggle Sidebar' }).click()
  await page.getByTestId('nav-voice-design').click()
  await page.getByTestId('engine-qwen').click()
  await page.getByTestId('voice-design-description').fill('Responsive library test voice')
  await page.getByTestId('voice-design-sample-text').fill('Reference text for the responsive voice library test.')
  await page.getByTestId('voice-design-generate-button').click()
  await expect(page.getByTestId('voice-design-result')).toBeVisible({ timeout: 30_000 })
  const save = page.getByRole('button', { name: /save to library/i }).first()
  if (await save.isVisible()) await save.click()
  if (!(await page.getByTestId('nav-voice-library').isVisible())) await page.getByRole('button', { name: 'Toggle Sidebar' }).click()
  await page.getByTestId('nav-voice-library').click()
  await expect(page.locator('[data-testid="voice-card"]')).toHaveCount(1)
}

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`voice card actions and analysis fit ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await ensureVoice(page)
    const card = page.locator('[data-testid="voice-card"]').first()
    await expect(card.getByRole('button', { name: 'Use in Speak' })).toBeVisible()
    await expect(card.getByRole('button', { name: /Edit audio/i })).toBeVisible()
    await expect(card.getByRole('button', { name: /Adjust pauses/i })).toBeVisible()
    await expect(card.getByRole('button', { name: 'More voice actions' })).toBeVisible()
    await expect(page.locator('body')).toHaveJSProperty('scrollWidth', viewport.width)

    await card.getByRole('button', { name: 'More voice actions' }).click()
    await expect(page.getByRole('button', { name: /Duplicate voice/i })).toBeVisible()
    await expect(page.getByText('Edit audio operations on a copy')).toBeVisible()

    await page.screenshot({ path: `test-results/voice-library-${viewport.width}.png`, fullPage: true })
  })
}
