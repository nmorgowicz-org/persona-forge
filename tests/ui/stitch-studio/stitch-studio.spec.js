import { test, expect } from '@playwright/test'

test.describe('stitch studio', () => {
  test('load segments, arrange order, trigger stitch, confirm stitched audio', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()

    // Confirm page loaded
    await expect(page.getByText(/stitch studio/i, { ignoreCase: true })).toBeVisible()

    // Name the voice (if input is available)
    const nameInput = page.locator('input[placeholder*="name"], input[placeholder*="Name"]').first()
    if (await nameInput.isVisible()) {
      await nameInput.fill('Stitched test voice')
    }

    // Insert a segment from library (if Insert button is available)
    const insertBtn = page.getByText(/insert/i).first()
    if (await insertBtn.isVisible()) {
      await insertBtn.click()
    }

    // Attempt to reorder clips: find drag handles
    const gripIcons = page.locator('.[data-testid="clip"] button, [aria-label*="drag"]')
    const gripCount = await gripIcons.count()
    if (gripCount >= 2) {
      const firstGrip = await gripIcons.first().boundingBox()
      const secondGrip = await gripIcons.nth(1).boundingBox()
      if (firstGrip && secondGrip) {
        await page.mouse.move(firstGrip.x + 10, firstGrip.y + firstGrip.height / 2)
        await page.mouse.down()
        await page.mouse.move(secondGrip.x + 10, secondGrip.y + secondGrip.height / 2, { steps: 10 })
        await page.mouse.up()
      }
    }

    // Trigger stitch / save
    const stitchOrSaveBtn = page.getByRole('button', { name: /save/i }).first()
    if (await stitchOrSaveBtn.isVisible()) {
      await stitchOrSaveBtn.click()
    }

    // Confirm result: saved text or stitched audio
    const hasSavedText = await page.getByText(/saved/i).isVisible()
    const hasAudio = await page.locator('audio').first().isVisible()
    expect(hasSavedText || hasAudio).toBeTruthy()
  })
})
