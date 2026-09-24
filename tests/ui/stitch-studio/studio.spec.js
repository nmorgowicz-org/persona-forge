import { test, expect } from '@playwright/test'
import { installLargeSegmentLibrary, makeTinyWavBuffer } from '../fixtures/largeSegmentLibrary.mjs'

async function insertNSegments(page, n) {
  await page.goto('/')
  await page.getByTestId('nav-stitch-studio').click()
  await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
  const items = page.getByTestId('stitch-picker-item-segments')
  await expect(items.first()).toBeVisible()
  for (let i = 0; i < n; i++) {
    await items.nth(i).click()
  }
  await page.getByTestId('stitch-picker-insert-segments').click()
  await expect(page.getByTestId('stitch-clip')).toHaveCount(n)
}
async function appendPickerItems(page, tab, count) {
  await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
  if (tab === 'voices') await page.getByRole('tab', { name: 'Reference voices' }).click()
  const items = page.getByTestId(`stitch-picker-item-${tab}`)
  await expect(items.first()).toBeVisible()
  for (let i = 0; i < count; i++) await items.nth(i).click()
  await page.getByTestId(`stitch-picker-insert-${tab}`).click()
}

async function setGap(page, index, value) {
  const gap = page.getByTestId('stitch-gap-control').nth(index)
  await gap.getByRole('button', { name: /Gap between clip/ }).click()
  const input = gap.getByRole('textbox', { name: /Gap between clip/ })
  await input.fill(value)
  await input.press('Enter')
}

// Mid-gesture pause for multi-segment drags: Framer Motion needs a render frame to
// recompute layout and register each threshold crossing. Waiting until the clip row's
// bounding boxes hold still across two consecutive animation frames is the settled
// end state itself -- a fixed 150ms sleep only guessed at how long that takes.
async function waitForDragLayoutSettled(page) {
  await page.waitForFunction(() => new Promise((resolve) => {
    const read = () => Array.from(document.querySelectorAll('[data-testid="stitch-clip"]'))
      .map((el) => {
        const r = el.getBoundingClientRect()
        return `${Math.round(r.x)},${Math.round(r.y)},${Math.round(r.width)}`
      })
      .join('|')
    const first = read()
    requestAnimationFrame(() => requestAnimationFrame(() => resolve(read() === first)))
  }), { timeout: 5000 })
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

    // Suggested punctuation gaps are defaults, not the values this positional-seam test is
    // about. Type explicit values before removing a clip.
    await setGap(page, 0, '150ms')
    await setGap(page, 1, '200ms')

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
    await setGap(page, 0, '150ms')
    await expect(page.locator('div[data-app-tooltip$="ms gap"]')).toHaveAttribute('data-app-tooltip', '150ms gap')

    await page.getByTestId('nav-voice-library').click()
    await page.getByTestId('voice-library-tab-segments').click()
    await page.getByRole('button', { name: 'Insert into Stitch Studio' }).nth(2).click()
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
    await page.getByRole('button', { name: 'Insert into Stitch Studio' }).first().click()
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

  test('quick insert Save and close commits the draft without navigating away from the caller page', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-library').click()
    await page.getByTestId('voice-library-tab-segments').click()
    await page.getByRole('button', { name: 'Insert into Stitch Studio' }).first().click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeVisible()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)

    await page.getByTestId('stitch-save-close').click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeHidden()
    // Unlike "Open in Stitch Studio", Save and close must not navigate away.
    await expect(page.getByTestId('nav-voice-library')).toHaveAttribute('data-active', 'true')
    await expect(page.getByTestId('nav-stitch-studio')).toHaveAttribute('data-active', 'false')

    await page.getByTestId('nav-stitch-studio').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)
  })

  test('quick insert X Escape and backdrop restore Voice Library focus', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-library').click()
    await page.getByTestId('voice-library-tab-segments').click()
    const launchButtons = page.getByRole('button', { name: 'Insert into Stitch Studio' })

    // Escape
    const escapeLaunch = launchButtons.first()
    await escapeLaunch.click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('stitch-editor-dialog')).toBeHidden()
    await expect(escapeLaunch).toBeFocused()

    // Backdrop click. Target the overlay element rather than a raw viewport coordinate: a
    // coordinate click can land before the overlay has settled (and that corner sits over the
    // sidebar, so a miss is not self-evident), leaving the dialog open. Wait for the overlay's
    // own enter animation first, so the outside-interaction is not swallowed mid-transition.
    const backdropLaunch = launchButtons.nth(1)
    await backdropLaunch.click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeVisible()
    const overlay = page.locator('[data-slot="dialog-overlay"]')
    await overlay.evaluate((el) =>
      Promise.all(el.getAnimations({ subtree: true }).map((a) => a.finished.catch(() => {}))),
    )
    await overlay.click({ position: { x: 4, y: 4 } })
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
    await page.getByRole('button', { name: 'Insert into Stitch Studio' }).nth(2).click()
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

    await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
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

    await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
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
    // Distinguishing text: the inserted row is the newest Podcast-Intros fixture
    // ("Segment number 248"); it can only sit at index 1 if the splice happened right
    // after the selected clip rather than appending at the very end. The original
    // second clip ("Segment number 250", the newest overall fixture) must remain last.
    await expect(clips.nth(1)).toContainText('Segment number 248')
    await expect(clips.nth(2)).toContainText('Segment number 250')
  })

  test('segment browser auditions only one row and does not eagerly request audio', async ({ page }) => {
    const { audioRequests } = await installLargeSegmentLibrary(page)
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()
    await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
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

  test('rapid audition clicks on different rows never let a slower request steal playback', async ({ page }) => {
    const { audioRequests } = await installLargeSegmentLibrary(page)
    let sawFirstRequest = false
    // A multi-second WAV -- the shared fixture's ~50ms clip would naturally finish playing
    // (firing 'ended') well inside this test's observation window, confounding the assertion.
    const longWav = makeTinyWavBuffer(3)
    await page.route('**/omnivoice/segments/*/audio', async (route) => {
      audioRequests.push(route.request().url())
      // The first row's fetch resolves slowly; the second row's must not be clobbered by it.
      if (!sawFirstRequest) {
        sawFirstRequest = true
        await new Promise((r) => setTimeout(r, 700))
      }
      await route.fulfill({ status: 200, contentType: 'audio/wav', body: longWav })
    })
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()
    await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
    await expect(page.getByTestId('segment-browser-dialog')).toBeVisible()
    await expect(page.getByTestId('stitch-picker-item-segments').first()).toBeVisible()

    const auditionButtons = page.getByTestId('segment-browser-audio')
    await auditionButtons.nth(0).click()
    await auditionButtons.nth(1).click()
    await expect.poll(() => audioRequests.length).toBe(2)
    await expect(auditionButtons.nth(1)).toHaveAttribute('data-playing', 'true')

    // Let row 0's slow, now-stale fetch resolve; it must not steal playback from row 1.
    await new Promise((r) => setTimeout(r, 900))
    await expect(auditionButtons.nth(1)).toHaveAttribute('data-playing', 'true')
    await expect(auditionButtons.nth(0)).toHaveAttribute('data-playing', 'false')
  })
  test('closing the segment browser cannot start playback from a fetch that resolved late', async ({ page }) => {
    // togglePlay uses a plain `new Audio()` instance, not a rendered <audio> element, so
    // querying the DOM can't observe it -- instrument the constructor instead to record every
    // play() call and when it happened relative to the dialog closing.
    await page.addInitScript(() => {
      window.__playCalls = []
      const OriginalAudio = window.Audio
      window.Audio = new Proxy(OriginalAudio, {
        construct(target, args) {
          const instance = new target(...args)
          const originalPlay = instance.play.bind(instance)
          instance.play = (...playArgs) => {
            window.__playCalls.push(Date.now())
            return originalPlay(...playArgs)
          }
          return instance
        },
      })
    })
    await installLargeSegmentLibrary(page)
    await page.route('**/omnivoice/segments/*/audio', async (route) => {
      await new Promise((r) => setTimeout(r, 700))
      await route.fulfill({ status: 200, contentType: 'audio/wav', body: makeTinyWavBuffer() })
    })
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()
    await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
    await expect(page.getByTestId('segment-browser-dialog')).toBeVisible()
    await expect(page.getByTestId('stitch-picker-item-segments').first()).toBeVisible()

    await page.getByTestId('segment-browser-audio').first().click()
    const closeTime = Date.now()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('segment-browser-dialog')).toBeHidden()

    // Give the in-flight fetch time to resolve after close; play() must never fire afterward.
    await new Promise((r) => setTimeout(r, 900))
    const playCallsAfterClose = await page.evaluate(
      (since) => (window.__playCalls ?? []).filter((t) => t >= since).length,
      closeTime,
    )
    expect(playCallsAfterClose).toBe(0)
  })

  test('segment browser Enter and double-click insert; Enter on a checkbox does not', async ({ page }) => {
    await installLargeSegmentLibrary(page)
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()
    const dialog = page.getByTestId('segment-browser-dialog')
    const items = page.getByTestId('stitch-picker-item-segments')
    const clips = page.getByTestId('stitch-clip')
    const openDialog = async () => {
      await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
      await expect(dialog).toBeVisible()
      await expect(items.first()).toBeVisible()
    }

    // (a) Enter with a selection and focus on the dialog surface (not on a row
    // control) inserts the selection.
    await openDialog()
    await items.nth(0).click()
    await dialog.focus()
    await page.keyboard.press('Enter')
    await expect(clips).toHaveCount(1)
    await expect(dialog).toBeHidden()

    // (b) Double-clicking a row inserts that row.
    await openDialog()
    const rows = page.locator('.segment-browser-row')
    await rows.nth(1).locator('p').first().dblclick()
    await expect(clips).toHaveCount(2)
    await expect(dialog).toBeHidden()

    // (c) Enter while a row checkbox is focused must not insert: the checkbox is an
    // interactive target the dialog's Enter handler does not intercept.
    await openDialog()
    await items.nth(2).click()
    await expect(items.nth(2)).toBeChecked()
    await page.keyboard.press('Enter')
    await expect(clips).toHaveCount(2)
    await expect(dialog).toBeVisible()
    await expect(items.nth(2)).toBeChecked()
  })
})

test.describe('Stitch Studio audio decode edge cases', () => {
  test('a segment whose audio fails to decode shows the No waveform fallback without crashing', async ({ page }) => {
    await installLargeSegmentLibrary(page)
    // Not valid audio -- decodeAudioData will reject, exercising the decode-failure path.
    await page.route('**/omnivoice/segments/*/audio', async (route) => {
      await route.fulfill({ status: 200, contentType: 'audio/wav', body: Buffer.from('not a real wav file') })
    })
    await insertNSegments(page, 1)
    await page.getByTestId('stitch-clip-edit-toggle').first().click()
    await expect(page.getByText('No waveform')).toBeVisible()
    // No crash: the clip still renders after the failed decode.
    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)
  })

  test('a clip trimmed to zero effective duration renders without NaN or negative widths', async ({ page }) => {
    await insertNSegments(page, 1)
    await page.getByTestId('stitch-clip-edit-toggle').first().click()
    const handle = page.getByTestId('stitch-trim-handle-left').first()
    const box = await handle.boundingBox()
    if (!box) throw new Error('trim handle has no bounding box')
    // Drag the left trim handle far past the clip's own width to fully trim it.
    await page.mouse.move(box.x + 1, box.y + box.height / 2)
    await page.mouse.down()
    await page.mouse.move(box.x + 4000, box.y + box.height / 2)
    await page.mouse.up()

    const clipWidth = await page.getByTestId('stitch-clip').first().evaluate((el) => el.getBoundingClientRect().width)
    expect(Number.isFinite(clipWidth)).toBe(true)
    expect(clipWidth).toBeGreaterThanOrEqual(0)
    const laneWidth = await page.getByTestId('stitch-waveform-canvas').first().evaluate((el) => el.getBoundingClientRect().width)
    expect(Number.isFinite(laneWidth)).toBe(true)
    expect(laneWidth).toBeGreaterThanOrEqual(0)
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
    await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
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

    // Two explicit zoom-in steps from the 2-clip Fit: each must land on a genuinely
    // new scale, and the ruler labels must stay strictly increasing (no duplicate
    // adjacent labels) at every zoom level, not only under auto-Fit.
    for (let zoomStep = 1; zoomStep <= 2; zoomStep++) {
      const zoomLevelBefore = await page.getByTestId('stitch-zoom-level').textContent()
      await page.getByTestId('stitch-zoom-in').click()
      await expect(page.getByTestId('stitch-zoom-level')).not.toHaveText(zoomLevelBefore)

      const ticks = await page.getByTestId('stitch-ruler-tick').all()
      expect(ticks.length).toBeGreaterThanOrEqual(2)
      const seconds = await Promise.all(ticks.map((t) => t.getAttribute('data-seconds').then(Number)))
      for (let i = 1; i < seconds.length; i++) {
        expect(seconds[i]).toBeGreaterThan(seconds[i - 1])
      }
    }
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
    expect(boxA).toBeTruthy()

    // Same 40px drag distance, delivered as one big jump vs many intermediate pointermove
    // events -- a delta computed fresh from the frozen gesture-start position on every move
    // (correct) lands on the same final value either way. A handler that instead adds the
    // per-event offset onto the live value (the pre-Packet-6 bug) compounds with each extra
    // pointermove and drifts further with more steps -- "acceleration" from event count alone.
    await page.mouse.move(boxA.x + boxA.width / 2, boxA.y + boxA.height / 2)
    await page.mouse.down()
    await page.mouse.move(boxA.x + boxA.width / 2 + 40, boxA.y + boxA.height / 2, { steps: 3 })
    await page.mouse.up()

    // The committed left-trim on clip A reflows the timeline (the Fit-zoom recompute
    // shifts card B and its trim handle ~20px), so a box captured before the drag is
    // stale: the second gesture's mouse.down would land in card B's waveform lane
    // (starting a region selection) instead of on the handle. Wait for the handle's
    // layout to settle, then re-query it.
    await page.waitForFunction(() => {
      const handle = document.querySelectorAll('[data-testid="stitch-trim-handle-left"]')[1]
      if (!handle) return false
      const rect = handle.getBoundingClientRect()
      const key = `${rect.x}|${rect.y}|${rect.width}|${rect.height}`
      if (window.__settledTrimHandleBox === key) return true
      window.__settledTrimHandleBox = key
      return false
    }, { timeout: 5000 })
    const boxB = await handles.nth(1).boundingBox()
    expect(boxB).toBeTruthy()

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
    await waitForDragLayoutSettled(page)
    await page.mouse.move(toBox.x + toBox.width - 5, toBox.y + 10, { steps: 10 })
    await waitForDragLayoutSettled(page)
    await page.mouse.up()

    const clipsAfter = await page.getByTestId('stitch-clip').evaluateAll((els) => els.map((el) => el.dataset.clipId))
    expect(clipsAfter).toEqual([clipsBefore[1], clipsBefore[2], clipsBefore[0]])
  })

  test('reorder then remove keeps the correct surviving seam value', async ({ page }) => {
    await insertNSegments(page, 3)
    const gapControls = page.getByTestId('stitch-gap-control')
    const typeIntoGap = async (index, text) => {
      await gapControls.nth(index).getByRole('button', { name: /^Gap between clip/ }).click()
      const input = gapControls.nth(index).locator('input')
      await input.fill(text)
      await input.press('Enter')
    }
    await typeIntoGap(0, '150')
    await typeIntoGap(1, '400')

    // Reorder first: seams are seam-indexed, not clip-identity-tied, so they must stay
    // 150ms/400ms after the permutation (same contract as the reorder-only test above).
    const firstClip = page.getByTestId('stitch-clip').nth(0)
    const lastClip = page.getByTestId('stitch-clip').nth(2)
    const fromBox = await firstClip.boundingBox()
    const toBox = await lastClip.boundingBox()
    await page.mouse.move(fromBox.x + fromBox.width / 2, fromBox.y + 10)
    await page.mouse.down()
    const midX = (fromBox.x + toBox.x) / 2
    await page.mouse.move(midX, toBox.y + 10, { steps: 10 })
    await waitForDragLayoutSettled(page)
    await page.mouse.move(toBox.x + toBox.width - 5, toBox.y + 10, { steps: 10 })
    await waitForDragLayoutSettled(page)
    await page.mouse.up()
    await expect(gapControls.nth(0)).toHaveAttribute('data-gap-ms', '150')
    await expect(gapControls.nth(1)).toHaveAttribute('data-gap-ms', '400')

    // Now remove the middle clip (position 1) -- the removal contract drops the seam that
    // followed the removed clip, so the surviving seam must be the leading one (150ms),
    // exercised together with a prior reorder rather than in isolation.
    await page.getByTestId('stitch-clip').nth(1).locator('[aria-label="Remove clip"]').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(2)
    await expect(gapControls).toHaveCount(1)
    await expect(gapControls.first()).toHaveAttribute('data-gap-ms', '150')
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
    await waitForDragLayoutSettled(page)
    await page.mouse.move(toBox.x + toBox.width - 5, toBox.y + 10, { steps: 10 })
    await waitForDragLayoutSettled(page)
    await page.mouse.up()

    await expect(gapControls.nth(0)).toHaveAttribute('data-gap-ms', '200')
    await expect(gapControls.nth(1)).toHaveAttribute('data-gap-ms', '400')
  })

  test('zero gap remains visible and distinguishable from non-zero gap', async ({ page }) => {
    await insertNSegments(page, 2)
    const gap = page.getByTestId('stitch-gap-control').first()
    await expect(gap).toBeVisible()
    await setGap(page, 0, '0')
    await expect(gap).toHaveAttribute('data-gap-zero', 'true')
    const zeroWidth = (await gap.boundingBox())?.width ?? 0

    for (let i = 0; i < 20; i++) await page.locator('button[aria-label="Increase gap"]').first().click()
    await expect(gap).toHaveAttribute('data-gap-zero', 'false')
    const nonZeroWidth = (await gap.boundingBox())?.width ?? 0
    expect(nonZeroWidth).toBeGreaterThan(zeroWidth)
  })

  test('keyboard selects clips and moves selection with arrow keys', async ({ page }) => {
    await insertNSegments(page, 3)
    const clips = page.getByTestId('stitch-clip')

    await clips.nth(0).click()
    await expect(clips.nth(0)).toHaveAttribute('data-selected', 'true')
    await page.keyboard.press('ArrowRight')
    await expect(clips.nth(1)).toHaveAttribute('data-selected', 'true')
    await expect(clips.nth(0)).toHaveAttribute('data-selected', 'false')
  })

  test('keyboard reorders the selected clip with Shift+Arrow', async ({ page }) => {
    await insertNSegments(page, 3)
    const clips = page.getByTestId('stitch-clip')
    const idsBefore = await clips.evaluateAll((els) => els.map((el) => el.dataset.clipId))

    await clips.nth(0).click()
    await page.keyboard.press('ArrowRight')
    await expect(clips.nth(1)).toHaveAttribute('data-selected', 'true')

    // Reorder the selected clip (index 1) one step left.
    await page.keyboard.press('Shift+ArrowLeft')
    const idsAfterReorder = await clips.evaluateAll((els) => els.map((el) => el.dataset.clipId))
    expect(idsAfterReorder).toEqual([idsBefore[1], idsBefore[0], idsBefore[2]])
    // Selection follows clipId, not position.
    await expect(clips.nth(0)).toHaveAttribute('data-selected', 'true')
  })

  test('keyboard nudges trim start with Arrow and Shift+Arrow', async ({ page }) => {
    await insertNSegments(page, 3)
    const clips = page.getByTestId('stitch-clip')
    await clips.nth(0).click()
    await page.getByTestId('stitch-clip-edit-toggle').nth(0).click()

    const before = Number(await page.getByTestId('stitch-stepper-trim-start-value').nth(0).textContent())
    await page.keyboard.press('ArrowUp')
    const after10 = Number(await page.getByTestId('stitch-stepper-trim-start-value').nth(0).textContent())
    expect(after10 - before).toBe(10)
    await page.keyboard.press('Shift+ArrowUp')
    const after110 = Number(await page.getByTestId('stitch-stepper-trim-start-value').nth(0).textContent())
    expect(after110 - after10).toBe(100)
  })

  test('keyboard removes the selected clip with Delete', async ({ page }) => {
    await insertNSegments(page, 3)
    const clips = page.getByTestId('stitch-clip')
    await clips.nth(0).click()
    const countBefore = await clips.count()
    await page.keyboard.press('Delete')
    await expect(clips).toHaveCount(countBefore - 1)
  })

  test('keyboard shortcuts never fire while focus is inside an editable control', async ({ page }) => {
    await insertNSegments(page, 3)
    const clips = page.getByTestId('stitch-clip')
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

test.describe('Stitch Studio readiness and save outcomes', () => {
  test('first clip names an untouched voice field and later clips never overwrite user input', async ({ page }) => {
    await insertNSegments(page, 1)

    const name = page.getByTestId('stitch-voice-name')
    await expect(name).not.toHaveValue('')
    await name.fill('My deliberate reference name')

    await appendPickerItems(page, 'segments', 1)
    await expect(page.getByTestId('stitch-clip')).toHaveCount(2)
    await expect(name).toHaveValue('My deliberate reference name')
  })

  test('punctuation creates visible suggested gaps and manual values are not overwritten', async ({ page }) => {
    await insertNSegments(page, 1)
    await appendPickerItems(page, 'segments', 1)

    const firstGap = page.getByTestId('stitch-gap-control').first()
    await expect(firstGap).toHaveAttribute('data-gap-ms', '520')
    await expect(page.getByTestId('stitch-gap-suggestion')).toContainText('Suggested from punctuation')

    await setGap(page, 0, '250ms')
    await expect(firstGap).toHaveAttribute('data-gap-ms', '250')

    await appendPickerItems(page, 'segments', 1)
    await expect(page.getByTestId('stitch-gap-control').first()).toHaveAttribute('data-gap-ms', '250')
    await expect(page.getByTestId('stitch-gap-control').nth(1)).toHaveAttribute('data-gap-ms', '520')
  })

  test('five seconds of gaps cannot satisfy the five-second source-material minimum', async ({ page }) => {
    await insertNSegments(page, 2)
    await page.getByTestId('stitch-voice-name').fill('Insufficient source material')

    // Leave only a sliver of the first source clip audible, then add the maximum permitted gap.
    const handle = page.getByTestId('stitch-trim-handle-left').first()
    const box = await handle.boundingBox()
    if (!box) throw new Error('trim handle has no bounding box')
    await page.mouse.move(box.x + 1, box.y + box.height / 2)
    await page.mouse.down()
    await page.mouse.move(box.x + 190, box.y + box.height / 2)
    await page.mouse.up()

    await setGap(page, 0, '5s')
    await expect(page.getByTestId('stitch-gap-control').first()).toHaveAttribute('data-gap-ms', '5000')
    await expect(page.getByTestId('stitch-save-voice')).toBeDisabled()
  })

  test('readiness distinguishes blocked, warning, ideal, and overlong states', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()
    await expect(page.getByTestId('stitch-reference-readiness')).toHaveAttribute('data-readiness-state', 'blocked')

    await appendPickerItems(page, 'segments', 3)
    await expect(page.getByTestId('stitch-reference-readiness')).toHaveAttribute('data-readiness-state', 'warning')

    await setGap(page, 0, '2s')
    await setGap(page, 1, '2s')
    await expect(page.getByTestId('stitch-reference-readiness')).toHaveAttribute('data-readiness-state', 'ideal')

    await setGap(page, 0, '5s')
    await setGap(page, 1, '5s')
    await expect(page.getByTestId('stitch-reference-readiness')).toHaveAttribute('data-readiness-state', 'overlong')
  })

  test('warning state with a name filled in shows exactly one primary action', async ({ page }) => {
    await insertNSegments(page, 3)
    await expect(page.getByTestId('stitch-preview-ready')).toBeVisible()
    await page.getByTestId('stitch-voice-name').fill('Warning state reference')
    await expect(page.getByTestId('stitch-reference-readiness')).toHaveAttribute('data-readiness-state', 'warning')

    // Punctuation-derived gap suggestions can retrigger the preview's 700ms debounced
    // re-render shortly after insert; clear that window so isPreviewRendering has settled
    // before reading button classes, or the assertion below can catch a transient mid-render
    // frame instead of the sustained steady state this test targets.
    await page.waitForTimeout(900)
    await expect(page.getByTestId('stitch-preview-ready')).toBeVisible()

    const saveButton = page.getByTestId('stitch-save-voice')
    const guidanceButton = page.getByTestId('stitch-guidance-primary')
    await expect(saveButton).toBeEnabled()
    await expect(guidanceButton).toBeVisible()
    // Capture both classes from the same DOM snapshot per poll -- two independently
    // polled assertions can each observe a different intermediate render and falsely agree.
    await expect.poll(async () => ({
      saveIsBrand: /btn-brand/.test((await saveButton.getAttribute('class')) ?? ''),
      guidanceIsBrand: /btn-brand/.test((await guidanceButton.getAttribute('class')) ?? ''),
    }), { timeout: 5000 }).toEqual({ saveIsBrand: false, guidanceIsBrand: true })
  })

  test('missing name disables save and focuses the name step', async ({ page }) => {
    await insertNSegments(page, 3)
    await setGap(page, 0, '2s')
    await setGap(page, 1, '2s')

    await expect(page.getByTestId('stitch-save-voice')).toBeDisabled()
    await page.getByTestId('stitch-guidance-primary').click()
    await expect(page.getByTestId('stitch-voice-name')).toBeFocused()
  })

  test('plain save does not activate the API default', async ({ page }) => {
    let activationRequests = 0
    await page.route('**/voices/*/activate', async (route) => {
      activationRequests += 1
      await route.continue()
    })
    await insertNSegments(page, 3)
    await page.getByTestId('stitch-voice-name').fill('Plain saved reference')
    await expect(page.getByTestId('stitch-save-voice')).toBeEnabled()
    await page.getByTestId('stitch-save-voice').click()

    await expect(page.getByText('Saved to voice library as')).toBeVisible()
    expect(activationRequests).toBe(0)
  })

  test('API default activation failure preserves the saved voice and offers retry', async ({ page }) => {
    let activationRequests = 0
    await page.route('**/voices/*/activate', async (route) => {
      activationRequests += 1
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: 'activation unavailable' }) })
    })
    await insertNSegments(page, 3)
    await page.getByTestId('stitch-voice-name').fill('Default saved reference')
    await page.getByTestId('stitch-use-as-api-default').check()
    await expect(page.getByTestId('stitch-save-voice')).toHaveText('Save & use as API default')
    await page.getByTestId('stitch-save-voice').click()

    await expect(page.getByText('Saved, not activated')).toBeVisible()
    await expect(page.getByTestId('stitch-retry-api-activation')).toBeVisible()
    expect(activationRequests).toBe(1)
  })
})
