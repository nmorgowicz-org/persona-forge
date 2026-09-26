import { test, expect } from '@playwright/test'

// Contract D17 / §6.11: the server keeps UI preferences in ui_preferences.json next to
// runtime.json; localStorage only holds a first-paint copy under each key's old name and
// encoding. `page.request` shares the page's browser context, so it reads the same store the
// page writes to.

async function serverPrefs(page) {
  const res = await page.request.get('/ui/preferences')
  expect(res.status()).toBe(200)
  return (await res.json()).values
}

test.describe('server-side UI preferences', () => {
  test('a theme set in the UI comes back from the server after localStorage is cleared', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'violet')

    const saved = page.waitForResponse(
      (res) => res.url().endsWith('/ui/preferences') && res.request().method() === 'POST',
    )
    await page.getByRole('button', { name: 'Teal', exact: true }).click()
    expect((await saved).status()).toBe(200)
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'teal')
    expect(await serverPrefs(page)).toMatchObject({ theme: 'teal' })

    // Empty localStorage before any app script runs on the reload, so nothing written by the
    // previous page (including a late background write) can survive into the new one.
    await page.addInitScript(() => {
      if (window.sessionStorage.getItem('ui-prefs-spec-cleared')) return
      window.localStorage.clear()
      window.sessionStorage.setItem('ui-prefs-spec-cleared', '1')
    })
    await page.reload()

    await expect(page.locator('html')).toHaveAttribute('data-theme', 'teal')
    // The server value was written back to the local copy for the next first paint.
    await expect
      .poll(() => page.evaluate(() => window.localStorage.getItem('persona-forge-theme')))
      .toBe('teal')
  })

  test('first load migrates old localStorage keys the server does not have yet', async ({ page }) => {
    // The server store is shared across this file's tests (one server per run): the theme key
    // is already server-owned by the earlier test, and the server WINS — so the seeded rose
    // theme must NOT be uploaded, while the four keys the server lacks must migrate.
    const seeded = {
      'persona-forge-theme': 'rose',
      'persona-forge-experience-level': 'expert',
      'voice-library-layout': 'grid-2',
      'voice-library-analysis-expanded': 'false',
      'pf-update-dismissed-version': '2.9.0',
    }
    await page.addInitScript((seed) => {
      for (const [key, value] of Object.entries(seed)) {
        window.localStorage.setItem(key, value)
      }
    }, seeded)
    await page.goto('/')
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'teal')

    await expect.poll(() => serverPrefs(page)).toMatchObject({
      experienceLevel: 'expert',
      'voiceLibrary.layout': 'grid-2',
      'voiceLibrary.analysisExpanded': false,
      'updates.dismissedVersion': '2.9.0',
    })
  })
})
