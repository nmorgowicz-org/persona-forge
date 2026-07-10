import { test, expect } from '@playwright/test'

const TEST_PROFILE = (process.env.TEST_PROFILE || '').trim().toLowerCase()

test.describe('generate', () => {
  test('typing text and generating produces audio', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('speak-text-input').fill('Hello from Playwright.')
    await page.getByTestId('speak-generate-button').click()
    await expect(page.getByTestId('speak-result')).toBeVisible({ timeout: 30000 })
    await expect(page.getByTestId('speak-result').locator('audio')).toHaveCount(1)
  })


  test('generate button stays disabled for empty text', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('speak-generate-button')).toBeDisabled()
  })

  test('error profile: generate error shows banner (when TEST_PROFILE=error_on_generate)', async ({ page }) => {
    // This test is meaningful when TEST_PROFILE=error_on_generate is set at the server level.
    // Without that profile, the same flow is just a normal happy path.
    await page.goto('/')
    await page.getByTestId('speak-text-input').fill('Error test.')
    await page.getByTestId('speak-generate-button').click()

    // Allow either error banner (profile active) or normal result (no profile)
    const errorBanner = page.getByTestId('speak-error')
    const resultArea = page.getByTestId('speak-result')
    await expect(errorBanner.or(resultArea)).toBeVisible({ timeout: 15000 })

    if (TEST_PROFILE === 'error_on_generate') {
      await expect(errorBanner).toBeVisible()
    } else {
      await expect(resultArea).toBeVisible()
    }
  })
})
