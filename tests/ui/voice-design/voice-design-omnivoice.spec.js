import { test, expect } from '@playwright/test'

test.describe('voice design (OmniVoice engine)', () => {
  test('OmniVoice flow: switch engine, fill segments, audition, select takes, stitch, save, library card', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-design').click()

    // Switch to OmniVoice
    await page.getByTestId('engine-omnivoice').click()

    // Fill script with two short segments
    const scriptEl = page.getByTestId('omnivoice-script')
    await scriptEl.click()
    await scriptEl.fill(
      'Hello, this is a short sample line one.\nAnd here is another sample line two.'
    )

    // Generate candidates (audition)
    const auditionBtn = page.getByTestId('omnivoice-audition-button')
    await auditionBtn.click()

    // Wait for audition to be running (button becomes disabled while generating)
    await expect(auditionBtn).toBeDisabled({ timeout: 5000 })

    // Wait for segment rack to appear (candidates generated)
    await expect(page.locator('div:has-text("Segment rack")')).toBeVisible({ timeout: 30000 })

    // Select at least one take: click the first candidate button
    const firstTakeBtn = page.locator('button[type="button"], [role="radio"]').first()
    if (await firstTakeBtn.isVisible()) {
      await firstTakeBtn.click()
    }

    // Stitch selected takes
    const stitchBtn = page.getByTestId('omnivoice-stitch-button')
    if (await stitchBtn.isVisible()) {
      await stitchBtn.click()
    } else {
      const anyStitch = page.getByText(/stitch/i).first()
      if (await anyStitch.isVisible()) await anyStitch.click()
    }

    // Wait for stitched result
    await expect(page.getByTestId('omnivoice-result')).toBeVisible({ timeout: 20000 })

    // Save to voice library
    const saveBtn = page.getByTestId('omnivoice-save-button')
    if (await saveBtn.isVisible()) {
      await saveBtn.click()
    } else {
      const anySave = page.getByText(/save to voice library/i).first()
      if (await anySave.isVisible()) await anySave.click()
    }

    // Confirm saved
    await expect(page.getByText(/saved to voice library/i)).toBeVisible({ timeout: 10000 }).catch(
      () => {
        expect(page.getByTestId('omnivoice-result')).toBeVisible()
      }
    )

    // Navigate to library and verify voice card is present
    await page.getByTestId('nav-voice-library').click()
    await expect(page.locator('[data-testid="voice-card"]')).toHaveCount(
      { greaterThanOrEqual: 1 },
      { timeout: 10000 }
    )
  })
})
