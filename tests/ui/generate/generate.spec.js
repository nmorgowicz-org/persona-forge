import { test, expect } from '@playwright/test'

test.describe('generate', () => {
  test('typing text and generating produces a playable result', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('speak-text-input').fill('Hello from Playwright.')
    await page.getByTestId('speak-generate-button').click()
    await expect(page.getByTestId('speak-result')).toBeVisible()
    await expect(page.getByTestId('speak-result').locator('audio')).toHaveCount(1)
  })

  test('generate button stays disabled for empty text', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('speak-generate-button')).toBeDisabled()
  })
})
