import { test, expect } from '@playwright/test'

async function insertNSegments(page, n) {
  await page.goto('/')
  await page.getByTestId('nav-stitch-studio').click()
  await page.getByTestId('stitch-picker-toggle-segments').click()
  const items = page.getByTestId('stitch-picker-item-segments')
  await expect(items.first()).toBeVisible()
  for (let i = 0; i < n; i++) {
    await items.nth(i).click()
  }
  await page.getByTestId('stitch-picker-insert-segments').click()
  await expect(page.getByTestId('stitch-clip')).toHaveCount(n)
}

test.describe('Stitch Studio durable plan domain', () => {
  test('region edits survive Stitch Studio unmount and remount', async ({ page }) => {
    await insertNSegments(page, 1)

    await page.getByTestId('stitch-clip-edit-toggle').first().click()
    await page.locator('button[data-app-tooltip="Apply gain to selected region"]').click()
    await expect(page.getByTestId('stitch-region-edit')).toHaveCount(1)

    // Unmount Stitch Studio by navigating away, then remount by navigating back.
    await page.getByTestId('nav-speak').click()
    await page.getByTestId('nav-stitch-studio').click()

    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)
    await page.getByTestId('stitch-clip-edit-toggle').first().click()
    await expect(
      page.getByTestId('stitch-region-edit'),
      'region edit must remain part of the durable plan across unmount/remount',
    ).toHaveCount(1)
  })

  test('removing a middle clip keeps later gap values on their seams', async ({ page }) => {
    await insertNSegments(page, 3)

    // Materialize both gaps (they start at 0ms / hidden behind a "+" affordance).
    const addGapButtons = page.locator('button[data-app-tooltip="Add a gap between these clips"]')
    await addGapButtons.nth(0).click() // seam 0 -> 200ms
    await addGapButtons.nth(0).click() // seam 1 (now first remaining "+") -> 200ms

    // Give the two seams distinct values: seam 0 -> 150ms, seam 1 stays 200ms.
    const decreaseSeam0 = page.locator('button[aria-label="Decrease gap"]').nth(0)
    for (let i = 0; i < 5; i++) {
      await decreaseSeam0.click()
    }

    const seams = page.locator('div[data-app-tooltip$="ms gap"]')
    await expect(seams).toHaveCount(2)
    await expect(seams.nth(0)).toHaveAttribute('data-app-tooltip', '150ms gap')
    await expect(seams.nth(1)).toHaveAttribute('data-app-tooltip', '200ms gap')

    // Remove the middle clip (index 1 of 3).
    await page.getByTestId('stitch-clip').nth(1).locator('[aria-label="Remove clip"]').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(2)

    // Locked contract: removal drops the seam that followed the removed clip, so the
    // surviving seam is the one that preceded it (150ms), not the trailing one (200ms).
    const survivingSeams = page.locator('div[data-app-tooltip$="ms gap"]')
    await expect(survivingSeams).toHaveCount(1)
    await expect(survivingSeams.first()).toHaveAttribute('data-app-tooltip', '150ms gap')
  })
})

test.describe('Stitch Studio preview lifecycle', () => {
  test('superseded preview render is aborted', async ({ page }) => {
    await insertNSegments(page, 2)
    await expect(page.getByTestId('stitch-preview-ready')).toBeVisible()

    const abortedRequests = []
    let requestCount = 0
    await page.route('**/omnivoice/stitch', async (route) => {
      requestCount += 1
      if (requestCount === 1) {
        // Hold the soon-to-be-superseded request open well past the second change's
        // debounce window, so it is still in flight when the newer render must abort it.
        await new Promise((resolve) => setTimeout(resolve, 2500))
      }
      await route.continue()
    })
    page.on('requestfailed', (req) => {
      if (req.url().includes('/omnivoice/stitch')) abortedRequests.push(req.failure()?.errorText ?? '')
    })

    // First change: materializes seam 0 at 200ms, scheduling a render ~700ms later.
    await page.locator('button[data-app-tooltip="Add a gap between these clips"]').first().click()

    // Second change, fired after the first request has gone out but while it is still
    // held open -- the resulting render must abort the first in-flight request.
    await page.waitForTimeout(900)
    await page.locator('button[aria-label="Decrease gap"]').first().click()

    await expect(page.getByTestId('stitch-preview-ready')).toHaveAttribute('data-plan-hash', /.+/, { timeout: 5000 })
    const hashAfterSecondChange = await page.getByTestId('stitch-preview-ready').getAttribute('data-plan-hash')

    // Give the stale first request time to resolve, if it were never aborted, and confirm
    // it never clobbers the fresher preview that the second render already applied.
    await page.waitForTimeout(2000)
    await expect(page.getByTestId('stitch-preview-ready')).toHaveAttribute('data-plan-hash', hashAfterSecondChange ?? '')
    expect(abortedRequests.some((reason) => /abort/i.test(reason))).toBe(true)
  })

  test('Studio preview URL is revoked on page unmount', async ({ page }) => {
    await insertNSegments(page, 1)
    await expect(page.getByTestId('stitch-preview-ready')).toBeVisible()
    const previewUrl = await page.locator('[data-testid="stitch-preview-ready"] audio').getAttribute('src')
    expect(previewUrl).toMatch(/^blob:/)

    await page.getByTestId('nav-speak').click()

    const fetchResult = await page.evaluate(async (url) => {
      try {
        await fetch(url)
        return 'ok'
      } catch {
        return 'rejected'
      }
    }, previewUrl)
    expect(fetchResult).toBe('rejected')

    await page.getByTestId('nav-stitch-studio').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)
    await expect(page.getByTestId('stitch-preview-ready')).toBeVisible()
    const newPreviewUrl = await page.locator('[data-testid="stitch-preview-ready"] audio').getAttribute('src')
    expect(newPreviewUrl).toMatch(/^blob:/)
    expect(newPreviewUrl).not.toBe(previewUrl)
  })
})
