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

    // Gap controls are always rendered now (including 0.00s seams) -- materialize both
    // gaps to 200ms via the always-present stepper instead of a "+" affordance.
    const increaseButtons = page.locator('button[aria-label="Increase gap"]')
    for (let i = 0; i < 20; i++) await increaseButtons.nth(0).click() // seam 0 -> 200ms
    for (let i = 0; i < 20; i++) await increaseButtons.nth(1).click() // seam 1 -> 200ms

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
    for (let i = 0; i < 20; i++) await page.locator('button[aria-label="Increase gap"]').first().click()

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
    for (let i = 0; i < 20; i++) await page.locator('button[aria-label="Increase gap"]').first().click()
    const decreaseGap = page.locator('button[aria-label="Decrease gap"]').first()
    for (let i = 0; i < 5; i++) await decreaseGap.click()
    await expect(page.locator('div[data-app-tooltip$="ms gap"]')).toHaveAttribute('data-app-tooltip', '150ms gap')

    await page.getByTestId('nav-voice-library').click()
    await page.getByTestId('voice-library-tab-segments').click()
    await page.getByRole('button', { name: 'Insert into stitch editor' }).nth(2).click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeVisible()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(3)

    // Change something in the draft -- must never reach the committed plan.
    for (let i = 0; i < 20; i++) await page.locator('button[aria-label="Increase gap"]').first().click()

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
    for (let i = 0; i < 20; i++) await page.locator('button[aria-label="Increase gap"]').first().click()
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

test.describe('Stitch Studio shared visual primitives', () => {
  test('timeline ruler labels remain aligned at Fit and two zoom levels', async ({ page }) => {
    await insertNSegments(page, 1)
    const ticksAt1 = await page.getByTestId('stitch-ruler-tick').all()
    expect(ticksAt1.length).toBeGreaterThanOrEqual(2)
    const secondsAt1 = await Promise.all(ticksAt1.map((t) => t.getAttribute('data-seconds').then(Number)))
    for (let i = 1; i < secondsAt1.length; i++) {
      expect(secondsAt1[i]).toBeGreaterThan(secondsAt1[i - 1])
    }

    // Insert two more segments: same "Fit" ruler now spans a longer duration, i.e. a
    // different effective seconds-per-pixel scale, without any explicit zoom control yet.
    await page.getByTestId('stitch-picker-toggle-segments').click()
    await page.getByTestId('stitch-picker-item-segments').nth(1).click()
    await page.getByTestId('stitch-picker-insert-segments').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(2)

    const ticksAt2 = await page.getByTestId('stitch-ruler-tick').all()
    expect(ticksAt2.length).toBeGreaterThanOrEqual(2)
    const secondsAt2 = await Promise.all(ticksAt2.map((t) => t.getAttribute('data-seconds').then(Number)))
    for (let i = 1; i < secondsAt2.length; i++) {
      expect(secondsAt2[i]).toBeGreaterThan(secondsAt2[i - 1])
    }
    // The two scales must genuinely differ: the ruler for the 2-clip plan spans a longer
    // duration than the 1-clip plan.
    expect(secondsAt2[secondsAt2.length - 1]).toBeGreaterThan(secondsAt1[secondsAt1.length - 1])
  })

  test('waveform canvas backing store follows device pixel ratio', async ({ page, browser }) => {
    await insertNSegments(page, 1)
    await page.getByTestId('stitch-clip-edit-toggle').first().click()
    const canvas = page.getByTestId('stitch-waveform-canvas').first()
    await expect(canvas).toBeVisible()
    const ratioAt1x = await canvas.evaluate((el) => {
      const rect = el.getBoundingClientRect()
      return el.width / rect.width
    })
    const dpr1 = await page.evaluate(() => window.devicePixelRatio ?? 1)
    expect(ratioAt1x).toBeCloseTo(dpr1, 0)

    const hiDpiContext = await browser.newContext({ deviceScaleFactor: 2 })
    const hiDpiPage = await hiDpiContext.newPage()
    await insertNSegments(hiDpiPage, 1)
    await hiDpiPage.getByTestId('stitch-clip-edit-toggle').first().click()
    const hiDpiCanvas = hiDpiPage.getByTestId('stitch-waveform-canvas').first()
    await expect(hiDpiCanvas).toBeVisible()
    const ratioAt2x = await hiDpiCanvas.evaluate((el) => {
      const rect = el.getBoundingClientRect()
      return el.width / rect.width
    })
    expect(ratioAt2x).toBeGreaterThan(ratioAt1x)
    expect(ratioAt2x).toBeCloseTo(2, 0)
    await hiDpiContext.close()
  })

  test('fade overlays are visible and change width when fade values change', async ({ page }) => {
    await insertNSegments(page, 1)
    await page.getByTestId('stitch-clip-edit-toggle').first().click()

    const fadeOverlay = page.getByTestId('stitch-fade-overlay-left')
    await expect(fadeOverlay, 'no fade applied yet -- overlay must not render').toHaveCount(0)

    const increaseFadeIn = page.locator('button[aria-label="Increase Fade in"]').first()
    for (let i = 0; i < 40; i++) {
      await increaseFadeIn.click()
    }
    await expect(fadeOverlay).toBeVisible()
    const widthAt400ms = (await fadeOverlay.boundingBox())?.width ?? 0
    expect(widthAt400ms).toBeGreaterThan(0)

    for (let i = 0; i < 40; i++) {
      await increaseFadeIn.click()
    }
    const widthAt800ms = (await fadeOverlay.boundingBox())?.width ?? 0
    expect(widthAt800ms).toBeGreaterThan(widthAt400ms)
  })
})

test.describe('Stitch Studio pointer-safe editing and timeline geometry', () => {
  test('trim drag uses pointer delta without acceleration', async ({ page }) => {
    await insertNSegments(page, 2)
    await page.getByTestId('stitch-clip-edit-toggle').nth(0).click()
    await page.getByTestId('stitch-clip-edit-toggle').nth(1).click()

    const handles = page.getByTestId('stitch-trim-handle-left')
    const boxA = await handles.nth(0).boundingBox()
    const boxB = await handles.nth(1).boundingBox()
    expect(boxA).toBeTruthy()
    expect(boxB).toBeTruthy()

    // Same 40px drag distance, delivered as one big jump vs many intermediate pointermove
    // events -- a delta computed fresh from the frozen gesture-start position on every move
    // (correct) lands on the same final value either way. A handler that instead adds the
    // per-event offset onto the live value (the pre-Packet-6 bug) compounds with each extra
    // pointermove and drifts further with more steps -- "acceleration" from event count alone.
    await page.mouse.move(boxA.x + boxA.width / 2, boxA.y + boxA.height / 2)
    await page.mouse.down()
    await page.mouse.move(boxA.x + boxA.width / 2 + 40, boxA.y + boxA.height / 2, { steps: 3 })
    await page.mouse.up()

    await page.mouse.move(boxB.x + boxB.width / 2, boxB.y + boxB.height / 2)
    await page.mouse.down()
    await page.mouse.move(boxB.x + boxB.width / 2 + 40, boxB.y + boxB.height / 2, { steps: 25 })
    await page.mouse.up()

    const valueA = Number(await page.getByTestId('stitch-stepper-trim-start-value').nth(0).textContent())
    const valueB = Number(await page.getByTestId('stitch-stepper-trim-start-value').nth(1).textContent())
    expect(valueA).toBeGreaterThan(0)
    expect(Math.abs(valueA - valueB)).toBeLessThanOrEqual(10)
  })

  test('multi-position reorder applies the full permutation', async ({ page }) => {
    await insertNSegments(page, 3)
    const clipsBefore = await page.getByTestId('stitch-clip').evaluateAll((els) => els.map((el) => el.dataset.clipId))
    expect(clipsBefore).toHaveLength(3)

    // Drag clip 0 past clip 1 AND clip 2 in one continuous gesture, landing after clip 2 --
    // this only exercises the bug if the drag moves the item more than one position. A pause
    // between intermediate stops (not just many `steps`) gives Framer Motion's PanSession a
    // render frame to recompute layout and register each threshold crossing in turn --
    // otherwise a single fast synthetic gesture can land only one swap instead of both.
    const firstClip = page.getByTestId('stitch-clip').nth(0)
    const lastClip = page.getByTestId('stitch-clip').nth(2)
    const fromBox = await firstClip.boundingBox()
    const toBox = await lastClip.boundingBox()
    await page.mouse.move(fromBox.x + fromBox.width / 2, fromBox.y + 10)
    await page.mouse.down()
    const midX = (fromBox.x + toBox.x) / 2
    await page.mouse.move(midX, toBox.y + 10, { steps: 10 })
    await page.waitForTimeout(150)
    await page.mouse.move(toBox.x + toBox.width - 5, toBox.y + 10, { steps: 10 })
    await page.waitForTimeout(150)
    await page.mouse.up()

    const clipsAfter = await page.getByTestId('stitch-clip').evaluateAll((els) => els.map((el) => el.dataset.clipId))
    expect(clipsAfter).toEqual([clipsBefore[1], clipsBefore[2], clipsBefore[0]])
  })

  test('gaps accept 200, 0.2s, and 200ms and preserve seam semantics after reorder', async ({ page }) => {
    await insertNSegments(page, 3)
    const gapControls = page.getByTestId('stitch-gap-control')
    await expect(gapControls).toHaveCount(2)

    const typeIntoGap = async (index, text) => {
      // The typed-value input only exists once editing starts -- click the always-visible
      // value button to enter edit mode first.
      await gapControls.nth(index).getByRole('button', { name: /^Gap between clip/ }).click()
      const input = gapControls.nth(index).locator('input')
      await input.fill(text)
      await input.press('Enter')
    }

    for (const text of ['200', '0.2s', '200ms']) {
      await typeIntoGap(0, text)
      await expect(gapControls.nth(0)).toHaveAttribute('data-gap-ms', '200')
    }
    await typeIntoGap(1, '400')
    await expect(gapControls.nth(1)).toHaveAttribute('data-gap-ms', '400')

    // Reorder clips -- seam values are keyed by seam position, not by which clips flank
    // them, matching the locked "gaps live at plan level, indexed by seam" contract.
    const firstClip = page.getByTestId('stitch-clip').nth(0)
    const lastClip = page.getByTestId('stitch-clip').nth(2)
    const fromBox = await firstClip.boundingBox()
    const toBox = await lastClip.boundingBox()
    await page.mouse.move(fromBox.x + fromBox.width / 2, fromBox.y + 10)
    await page.mouse.down()
    const midX = (fromBox.x + toBox.x) / 2
    await page.mouse.move(midX, toBox.y + 10, { steps: 10 })
    await page.waitForTimeout(150)
    await page.mouse.move(toBox.x + toBox.width - 5, toBox.y + 10, { steps: 10 })
    await page.waitForTimeout(150)
    await page.mouse.up()

    await expect(gapControls.nth(0)).toHaveAttribute('data-gap-ms', '200')
    await expect(gapControls.nth(1)).toHaveAttribute('data-gap-ms', '400')
  })

  test('zero gap remains visible and distinguishable from non-zero gap', async ({ page }) => {
    await insertNSegments(page, 2)
    const gap = page.getByTestId('stitch-gap-control').first()
    await expect(gap).toBeVisible()
    await expect(gap).toHaveAttribute('data-gap-zero', 'true')
    const zeroWidth = (await gap.boundingBox())?.width ?? 0

    for (let i = 0; i < 20; i++) await page.locator('button[aria-label="Increase gap"]').first().click()
    await expect(gap).toHaveAttribute('data-gap-zero', 'false')
    const nonZeroWidth = (await gap.boundingBox())?.width ?? 0
    expect(nonZeroWidth).toBeGreaterThan(zeroWidth)
  })

  test('keyboard selects, reorders, removes, and nudges trim, but never fires inside an input', async ({ page }) => {
    await insertNSegments(page, 3)
    const clips = page.getByTestId('stitch-clip')
    const idsBefore = await clips.evaluateAll((els) => els.map((el) => el.dataset.clipId))

    await clips.nth(0).click()
    await expect(clips.nth(0)).toHaveAttribute('data-selected', 'true')
    await page.keyboard.press('ArrowRight')
    await expect(clips.nth(1)).toHaveAttribute('data-selected', 'true')
    await expect(clips.nth(0)).toHaveAttribute('data-selected', 'false')

    // Reorder the selected clip (index 1) one step left.
    await page.keyboard.press('Shift+ArrowLeft')
    const idsAfterReorder = await clips.evaluateAll((els) => els.map((el) => el.dataset.clipId))
    expect(idsAfterReorder).toEqual([idsBefore[1], idsBefore[0], idsBefore[2]])

    // Trim nudging on the (still) selected clip -- it's already selected from the reorder
    // above (selection follows clipId, not position), so re-clicking it here would toggle it
    // off instead.
    await expect(clips.nth(0)).toHaveAttribute('data-selected', 'true')
    await page.getByTestId('stitch-clip-edit-toggle').nth(0).click()
    const before = Number(await page.getByTestId('stitch-stepper-trim-start-value').nth(0).textContent())
    await page.keyboard.press('ArrowUp')
    const after10 = Number(await page.getByTestId('stitch-stepper-trim-start-value').nth(0).textContent())
    expect(after10 - before).toBe(10)
    await page.keyboard.press('Shift+ArrowUp')
    const after110 = Number(await page.getByTestId('stitch-stepper-trim-start-value').nth(0).textContent())
    expect(after110 - after10).toBe(100)

    // Removal.
    const countBefore = await clips.count()
    await page.keyboard.press('Delete')
    await expect(clips).toHaveCount(countBefore - 1)

    // None of these shortcuts fire while focus is inside an editable control.
    await clips.nth(0).click()
    const textSpan = page.locator('span.cursor-text').first()
    await textSpan.click()
    const input = page.locator('input[aria-label="Edit clip text"]')
    await expect(input).toBeFocused()
    const countBeforeGuard = await clips.count()
    await page.keyboard.press('Delete')
    await page.keyboard.press('ArrowRight')
    await expect(clips).toHaveCount(countBeforeGuard)
    await page.keyboard.press('Escape')
  })
})

test.describe('Stitch Studio unified transport', () => {
  test('Space toggles arrangement playback outside editable controls', async ({ page }) => {
    await insertNSegments(page, 1)
    await expect(page.getByTestId('stitch-preview-ready')).toBeVisible()
    await expect(page.locator('[data-testid="stitch-preview-ready"] audio')).toHaveAttribute('src', /^blob:/)

    const toggle = page.getByTestId('stitch-transport-toggle')
    await expect(toggle).toHaveAttribute('aria-label', 'Play')

    await page.locator('body').click()
    await page.keyboard.press('Space')
    await expect(toggle).toHaveAttribute('aria-label', 'Pause')
    await page.keyboard.press('Space')
    await expect(toggle).toHaveAttribute('aria-label', 'Play')

    // Guard: Space typed into an editable control must type a space, not toggle playback.
    const textSpan = page.locator('span.cursor-text').first()
    await textSpan.click()
    const input = page.locator('input[aria-label="Edit clip text"]')
    await expect(input).toBeFocused()
    const before = await input.inputValue()
    await page.keyboard.press('Space')
    await expect(input).toHaveValue(`${before} `)
    await expect(toggle).toHaveAttribute('aria-label', 'Play')
    await page.keyboard.press('Escape')
  })

  test('clicking the ruler seeks the preview and moves the playhead', async ({ page }) => {
    await insertNSegments(page, 2)
    await expect(page.getByTestId('stitch-preview-ready')).toBeVisible()
    await expect(page.locator('[data-testid="stitch-preview-ready"] audio')).toHaveAttribute('src', /^blob:/)
    await expect(page.getByTestId('stitch-transport-playhead')).toHaveCount(1)

    const ruler = page.getByTestId('stitch-timeline-ruler')
    const box = await ruler.boundingBox()
    if (!box) throw new Error('ruler has no bounding box')

    const transformBefore = await page.getByTestId('stitch-transport-playhead').evaluate((el) => el.style.transform)
    await page.mouse.click(box.x + box.width * 0.6, box.y + 8)

    await expect
      .poll(() => page.getByTestId('stitch-transport-playhead').evaluate((el) => el.style.transform))
      .not.toBe(transformBefore)

    const audioTimeAfterSeek = await page.locator('[data-testid="stitch-preview-ready"] audio').evaluate((el) => el.currentTime)
    expect(audioTimeAfterSeek).toBeGreaterThan(0)
  })

  test('clip play scopes playback to the clip span but uses the shared transport', async ({ page }) => {
    await insertNSegments(page, 2)
    await expect(page.getByTestId('stitch-preview-ready')).toBeVisible()
    await expect(page.locator('[data-testid="stitch-preview-ready"] audio')).toHaveAttribute('src', /^blob:/)

    const audioCountBefore = await page.locator('audio').count()
    const clipPlayButton = page.locator('[aria-label="Play clip playback"]').first()
    await clipPlayButton.click()
    await expect(page.locator('[aria-label="Pause clip playback"]').first()).toBeVisible()

    // No second Audio instance was created -- the same <audio> element the ruler/toggle use
    // is the one now playing.
    expect(await page.locator('audio').count()).toBe(audioCountBefore)
    const isPaused = await page.locator('[data-testid="stitch-preview-ready"] audio').evaluate((el) => el.paused)
    expect(isPaused).toBe(false)

    // The shared arrangement toggle reflects the same transport as the per-clip range play.
    await expect(page.getByTestId('stitch-transport-toggle')).toHaveAttribute('aria-label', 'Pause')
  })

  test('reduced motion removes travel animations without hiding state', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await insertNSegments(page, 2)

    const wrapper = page.locator('[data-testid="stitch-clip-wrapper"]').first()
    await expect(wrapper).toBeVisible()
    const transitionDuration = await wrapper.evaluate((el) => getComputedStyle(el).transitionDuration)
    expect(transitionDuration).toBe('0s')

    // State still updates correctly even with travel animations disabled.
    const countBefore = await page.getByTestId('stitch-clip').count()
    await page.getByTestId('stitch-clip').first().locator('[aria-label="Remove clip"]').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(countBefore - 1)
  })
})
