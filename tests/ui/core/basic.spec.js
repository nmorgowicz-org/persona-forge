import { test, expect } from '@playwright/test'

test.describe('core', () => {
  test('/health returns ok', async ({ request, baseURL }) => {
    const res = await request.get(`${baseURL}/health`)
    expect(res.ok()).toBeTruthy()
    const body = await res.json()
    expect(body.status).toBe('ok')
  })

  test('home page loads with Speak active and speak text input present', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('nav-speak')).toBeVisible()
    await expect(page.getByTestId('speak-text-input')).toBeVisible()
  })

  test('all main nav items are clickable', async ({ page }) => {
    await page.goto('/')
    const navItems = [
      'nav-speak',
      'nav-voice-design',
      'nav-voice-library',
      'nav-stitch-studio',
      'nav-integrations',
      'nav-runtime',
    ]
    for (const id of navItems) {
      await expect(page.getByTestId(id)).toBeVisible()
      await page.getByTestId(id).click()
      await expect(page.getByTestId(id)).toBeVisible()
    }
  })
})
