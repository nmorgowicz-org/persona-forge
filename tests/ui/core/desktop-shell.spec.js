import { test, expect } from '@playwright/test'

// Contract D20/§6.10 desktop marker. In the real desktop app the shell's main-window
// initialization script sets window.__PERSONA_FORGE_DESKTOP__ before any page script runs;
// these specs simulate that the same way the shell's init script would, and assert the SPA
// applies the marker (data-desktop) and the macOS-only CSS scoped under it, leaving every
// other environment (browsers, Docker, the Windows/Linux app) exactly as before.

test.describe('desktop shell marker (D20)', () => {
  test('macos: data-desktop tag, transparent sidebar/body, opaque content column', async ({ page }) => {
    await page.addInitScript(() => {
      window.__PERSONA_FORGE_DESKTOP__ = { platform: 'macos' }
    })
    await page.goto('/')
    await expect(page.locator('html')).toHaveAttribute('data-desktop', 'macos')

    // Contract §6.10: body, the sidebar wrapper and the sidebar surface are transparent so the
    // native material shows through; the content column (sidebar-inset) is opaque.
    const bodyBg = page.locator('body').evaluate((el) => getComputedStyle(el).backgroundColor)
    expect(await bodyBg).toBe('rgba(0, 0, 0, 0)')

    const sidebarBg = page
      .locator('[data-slot="sidebar"]')
      .first()
      .evaluate((el) => getComputedStyle(el).backgroundColor)
    expect(await sidebarBg).toBe('rgba(0, 0, 0, 0)')

    const insetBg = page
      .locator('[data-slot="sidebar-inset"]')
      .first()
      .evaluate((el) => getComputedStyle(el).backgroundColor)
    expect(await insetBg).not.toBe('rgba(0, 0, 0, 0)')
  })

  test('windows: data-desktop tag but opaque backgrounds (CSS is macOS-only)', async ({ page }) => {
    await page.addInitScript(() => {
      window.__PERSONA_FORGE_DESKTOP__ = { platform: 'windows' }
    })
    await page.goto('/')
    await expect(page.locator('html')).toHaveAttribute('data-desktop', 'windows')

    const sidebarBg = page
      .locator('[data-slot="sidebar"]')
      .first()
      .evaluate((el) => getComputedStyle(el).backgroundColor)
    // Not a macOS-transparent value; anything opaque (the default sidebar surface) is fine.
    expect(await sidebarBg).not.toBe('rgba(0, 0, 0, 0)')
  })

  test('a plain browser: no data-desktop attribute, opaque body', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('html')).not.toHaveAttribute('data-desktop')
    const bodyBg = page.locator('body').evaluate((el) => getComputedStyle(el).backgroundColor)
    expect(await bodyBg).not.toBe('rgba(0, 0, 0, 0)')
  })
})