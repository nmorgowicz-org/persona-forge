import { test, expect } from '@playwright/test'
import { installLargeSegmentLibrary } from '../fixtures/largeSegmentLibrary.mjs'

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

test.describe('Stitch Studio quick-insert transaction', () => {
  test('quick insert cancel preserves the committed stitch plan', async ({ page }) => {
    await insertNSegments(page, 2)
    await page.locator('button[data-app-tooltip="Add a gap between these clips"]').first().click()
    const decreaseGap = page.locator('button[aria-label="Decrease gap"]').first()
    for (let i = 0; i < 5; i++) await decreaseGap.click()
    await expect(page.locator('div[data-app-tooltip$="ms gap"]')).toHaveAttribute('data-app-tooltip', '150ms gap')

    await page.getByTestId('nav-voice-library').click()
    await page.getByTestId('voice-library-tab-segments').click()
    await page.getByRole('button', { name: 'Insert into stitch editor' }).nth(2).click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeVisible()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(3)

    // Change something in the draft -- must never reach the committed plan.
    await page.locator('button[data-app-tooltip="Add a gap between these clips"]').first().click()

    await page.getByTestId('stitch-cancel-draft').click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeHidden()

    await page.getByTestId('nav-stitch-studio').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(2)
    await expect(page.locator('div[data-app-tooltip$="ms gap"]')).toHaveAttribute('data-app-tooltip', '150ms gap')
  })

  test('region edits survive quick insert commit into Studio', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-library').click()
    await page.getByTestId('voice-library-tab-segments').click()
    await page.getByRole('button', { name: 'Insert into stitch editor' }).first().click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeVisible()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)

    await page.getByTestId('stitch-clip-edit-toggle').first().click()
    await page.locator('button[data-app-tooltip="Apply gain to selected region"]').click()
    await expect(page.getByTestId('stitch-region-edit')).toHaveCount(1)

    await page.getByTestId('stitch-open-studio').click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeHidden()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)
    await page.getByTestId('stitch-clip-edit-toggle').first().click()
    await expect(
      page.getByTestId('stitch-region-edit'),
      'region edit made in the quick-insert draft must survive the commit into Studio',
    ).toHaveCount(1)
  })

  test('quick insert X Escape and backdrop restore Voice Library focus', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-library').click()
    await page.getByTestId('voice-library-tab-segments').click()
    const launchButtons = page.getByRole('button', { name: 'Insert into stitch editor' })

    // Escape
    const escapeLaunch = launchButtons.first()
    await escapeLaunch.click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('stitch-editor-dialog')).toBeHidden()
    await expect(escapeLaunch).toBeFocused()

    // Backdrop click
    const backdropLaunch = launchButtons.nth(1)
    await backdropLaunch.click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeVisible()
    await page.mouse.click(4, 4)
    await expect(page.getByTestId('stitch-editor-dialog')).toBeHidden()
    await expect(backdropLaunch).toBeFocused()

    // X close button
    const xLaunch = launchButtons.nth(2)
    await xLaunch.click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeVisible()
    await page.getByRole('button', { name: 'Close', exact: true }).click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeHidden()
    await expect(xLaunch).toBeFocused()
  })

  test('cancelled quick insert cannot replace Studio preview', async ({ page }) => {
    await insertNSegments(page, 2)
    await expect(page.getByTestId('stitch-preview-ready')).toBeVisible()
    const committedHash = await page.getByTestId('stitch-preview-ready').getAttribute('data-plan-hash')

    await page.getByTestId('nav-voice-library').click()
    await page.getByTestId('voice-library-tab-segments').click()
    await page.getByRole('button', { name: 'Insert into stitch editor' }).nth(2).click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeVisible()
    await page.locator('button[data-app-tooltip="Add a gap between these clips"]').first().click()
    await page.getByTestId('stitch-cancel-draft').click()

    await page.getByTestId('nav-stitch-studio').click()
    await expect(page.getByTestId('stitch-preview-ready')).toHaveAttribute('data-plan-hash', committedHash ?? '')
  })
})

test.describe('Voice Library discoverability and segment browser scale', () => {
  test('Voice Library switches between Reference voices and Segments without scrolling', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-library').click()

    await expect(page.getByTestId('voice-library-tab-voices')).toBeVisible()
    await expect(page.getByRole('heading', { name: /^Saved voices/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: /^Saved segments/ })).toBeHidden()

    await page.getByTestId('voice-library-tab-segments').click()
    await expect(page.getByRole('heading', { name: /^Saved segments/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: /^Saved voices/ })).toBeHidden()

    // Persists across reload.
    await page.reload()
    await page.getByTestId('nav-voice-library').click()
    await expect(page.getByRole('heading', { name: /^Saved segments/ })).toBeVisible()
  })

  test('segment browser filters by project and inserts selected assets after the selected clip', async ({ page }) => {
    const { projectNames } = await installLargeSegmentLibrary(page)
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()

    await page.getByTestId('stitch-picker-toggle-segments').click()
    await expect(page.getByTestId('segment-browser-dialog')).toBeVisible()
    const allItems = page.getByTestId('stitch-picker-item-segments')
    await allItems.nth(0).click()
    await allItems.nth(1).click()
    await page.getByTestId('stitch-picker-insert-segments').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(2)

    const firstClipId = await page.getByTestId('stitch-clip').first().getAttribute('data-clip-id')

    // Select the first clip, then insert a third via a project-filtered search -- it must
    // land right after the selected clip, not appended at the very end.
    await page.getByTestId('stitch-clip').first().click()

    await page.getByTestId('stitch-picker-toggle-segments').click()
    await expect(page.getByTestId('segment-browser-dialog')).toBeVisible()
    await page.getByTestId('segment-browser-project-filter').selectOption({ label: projectNames[2] })
    const filtered = page.getByTestId('stitch-picker-item-segments')
    await expect(filtered.first()).toBeVisible()
    const filteredCount = await filtered.count()
    expect(filteredCount).toBeGreaterThan(0)
    expect(filteredCount).toBeLessThan(250)
    await filtered.first().click()
    await page.getByTestId('stitch-picker-insert-segments').click()

    const clips = page.getByTestId('stitch-clip')
    await expect(clips).toHaveCount(3)
    await expect(clips.nth(0)).toHaveAttribute('data-clip-id', firstClipId ?? '')
    await expect(clips.nth(1)).toContainText('Segment number')
  })

  test('segment browser auditions only one row and does not eagerly request audio', async ({ page }) => {
    const { audioRequests } = await installLargeSegmentLibrary(page)
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()
    await page.getByTestId('stitch-picker-toggle-segments').click()
    await expect(page.getByTestId('segment-browser-dialog')).toBeVisible()
    await expect(page.getByTestId('stitch-picker-item-segments').first()).toBeVisible()

    expect(audioRequests.length).toBe(0)

    const auditionButtons = page.getByTestId('segment-browser-audio')
    await auditionButtons.nth(0).click()
    await expect.poll(() => audioRequests.length).toBe(1)

    await auditionButtons.nth(1).click()
    await expect.poll(() => audioRequests.length).toBe(2)
    await expect(auditionButtons.nth(0)).toHaveAttribute('data-playing', 'false')
  })
})
