import { test, expect } from '@playwright/test'

test.describe('performance', () => {
  test('page interactive within 5s', async ({ page }) => {
    const start = Date.now()
    await page.goto('/')
    await expect(page.getByTestId('speak-text-input')).toBeVisible({ timeout: 5000 })
    const elapsed = Date.now() - start
    expect(elapsed).toBeLessThan(5000)
  })

  test('navigate all pages, no console errors', async ({ page }) => {
    const errors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text())
      }
    })

    await page.goto('/')
    const pages = [
      'nav-speak',
      'nav-voice-design',
      'nav-voice-library',
      'nav-stitch-studio',
      'nav-integrations',
      'nav-runtime',
    ]
    for (const nav of pages) {
      await page.getByTestId(nav).click()
      await page.waitForTimeout(300)
    }

    // Filter known noise
    const realErrors = errors.filter(
      (e) =>
        !e.includes('favicon') &&
        !e.includes('404') &&
        !e.toLowerCase().includes('net::')
    )
    console.log('CONSOLE-ERRORS-DEBUG', JSON.stringify(realErrors, null, 2))
    expect(realErrors.length).toBe(0)
  })
})
