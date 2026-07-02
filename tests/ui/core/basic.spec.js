import { test, expect } from '@playwright/test'

test.describe('core', () => {
  test('/health returns ok', async ({ request, baseURL }) => {
    const res = await request.get(`${baseURL}/health`)
    expect(res.ok()).toBeTruthy()
    const body = await res.json()
    expect(body.status).toBe('ok')
  })

  test('home page loads with Speak active', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('nav-speak')).toBeVisible()
    await expect(page.getByTestId('speak-text-input')).toBeVisible()
  })

  test('sidebar navigates between every page', async ({ page }) => {
    await page.goto('/')
    const pages = [
      ['nav-voice-design', 'voice-design-description'],
      ['nav-voice-library', null],
      ['nav-integrations', null],
      ['nav-runtime', null],
      ['nav-speak', 'speak-text-input'],
    ]
    for (const [navTestId, contentTestId] of pages) {
      await page.getByTestId(navTestId).click()
      if (contentTestId) await expect(page.getByTestId(contentTestId)).toBeVisible()
    }
  })
})
