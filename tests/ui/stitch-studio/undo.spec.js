import { test, expect } from '@playwright/test'

// A-6 (T2): bounded, session-local undo/redo of complete StitchPlanState snapshots.
// Plan: docs/plans/20260922-premium_audio_plugin_ux.md T2 (a deliberate, owner-approved
// exception to the 2026-09-20 "no undo/history" constraint); runbook card A-6.
//
// RED-first: every test must fail on unmodified code because the feature is missing.

async function openStudio(page) {
  await page.goto('/')
  await page.getByTestId('nav-stitch-studio').click()
}

async function insertSegments(page, n) {
  await openStudio(page)
  await page.getByTestId('stitch-picker-toggle-segments').click()
  const items = page.getByTestId('stitch-picker-item-segments')
  await expect(items.first()).toBeVisible()
  for (let i = 0; i < n; i++) await items.nth(i).click()
  await page.getByTestId('stitch-picker-insert-segments').click()
  await expect(page.getByTestId('stitch-clip')).toHaveCount(n)
}

async function openFirstClipEditor(page) {
  await page.getByTestId('stitch-clip').first().click()
  await page.getByTestId('stitch-clip-edit-toggle').first().click()
  await expect(page.getByTestId('stitch-trim-handle-left').first()).toBeVisible()
}

const depth = (page) => page.getByTestId('stitch-undo').getAttribute('data-history-depth')

/** Drags an element horizontally by `dx` pixels with real pointer events. */
async function dragBy(page, locator, dx) {
  const box = await locator.boundingBox()
  const y = box.y + box.height / 2
  await page.mouse.move(box.x + box.width / 2, y)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + dx, y, { steps: 6 })
  await page.mouse.up()
}

test.describe('A-6: stitch editor undo/redo', () => {
  test('undo and redo restore a removed clip from the keyboard', async ({ page }) => {
    await insertSegments(page, 2)
    await page.getByTestId('stitch-clip').first().getByRole('button', { name: 'Remove clip' }).click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)

    await page.keyboard.press('ControlOrMeta+z')
    await expect(page.getByTestId('stitch-clip')).toHaveCount(2)

    await page.keyboard.press('ControlOrMeta+Shift+z')
    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)
  })

  test('one trim drag is one history entry', async ({ page }) => {
    await insertSegments(page, 1)
    await openFirstClipEditor(page)
    const trimStart = page.getByTestId('stitch-stepper-trim-start-value').first()
    await expect(trimStart).toHaveText('0')

    await dragBy(page, page.getByTestId('stitch-trim-handle-left').first(), 24)
    expect(Number(await trimStart.textContent())).toBeGreaterThan(0)

    // A single undo must land on the pre-drag value: a drag that recorded one entry per
    // pointermove would leave a mid-drag value here.
    await page.keyboard.press('ControlOrMeta+z')
    await expect(trimStart).toHaveText('0')
  })

  test('a scrubbed value is one entry per gesture', async ({ page }) => {
    await insertSegments(page, 1)
    await openFirstClipEditor(page)
    const trimStart = page.getByTestId('stitch-stepper-trim-start-value').first()
    await expect(trimStart).toHaveText('0')

    // The shared drag-scrub hook is a different commit path from the card's own handles: it
    // tracks the gesture locally and commits once on release. A commit per pointermove would
    // leave a mid-drag value after one undo.
    await dragBy(page, trimStart, 40)
    expect(Number(await trimStart.textContent())).toBeGreaterThan(0)

    await page.keyboard.press('ControlOrMeta+z')
    await expect(trimStart).toHaveText('0')
  })

  test('a burst of wheel notches on one control is a single entry', async ({ page }) => {
    await insertSegments(page, 1)
    await openFirstClipEditor(page)
    const before = await depth(page)
    const trimStart = page.getByTestId('stitch-stepper-trim-start-value').first()
    await expect(trimStart).toHaveText('0')

    // The wheel handler commits once per event, so a burst is several plan writes. They are
    // one adjustment to the user, and must therefore be one entry. (The seam deliberately has
    // no wheel -- it lives in the horizontal scroll container -- so this uses a stepper.)
    const box = await trimStart.boundingBox()
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    for (let i = 0; i < 3; i++) await page.mouse.wheel(0, -100)
    await expect(trimStart).toHaveText('30')
    expect(await depth(page)).toBe(String(Number(before) + 1))

    await page.keyboard.press('ControlOrMeta+z')
    await expect(trimStart).toHaveText('0')
  })

  test('history controls track the ends of the stack', async ({ page }) => {
    await openStudio(page)
    const undo = page.getByTestId('stitch-undo')
    const redo = page.getByTestId('stitch-redo')
    await expect(undo).toBeVisible()
    await expect(redo).toBeVisible()
    await expect(undo).toBeDisabled()
    await expect(redo).toBeDisabled()

    await page.getByTestId('stitch-picker-toggle-segments').click()
    const items = page.getByTestId('stitch-picker-item-segments')
    await expect(items.first()).toBeVisible()
    await items.first().click()
    await page.getByTestId('stitch-picker-insert-segments').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)
    await expect(undo).toBeEnabled()
    await expect(redo).toBeDisabled()
    expect(await depth(page)).toBe('1')

    // The controls must survive an empty plan, or undoing the first insert would strand the
    // redo with no way back.
    await undo.click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(0)
    await expect(undo).toBeDisabled()
    await expect(redo).toBeEnabled()

    await redo.click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)
    await expect(redo).toBeDisabled()
  })

  test('undo while typing in a text field leaves the plan alone', async ({ page }) => {
    await insertSegments(page, 2)
    await page.getByTestId('stitch-clip').first().locator('span.cursor-text').click()
    const input = page.getByLabel('Edit clip text')
    await expect(input).toBeFocused()
    await input.fill('typed reference text')

    await page.keyboard.press('ControlOrMeta+z')

    // The plan is untouched: nothing was undone, so both clips are still there.
    await expect(page.getByTestId('stitch-clip')).toHaveCount(2)
    expect(await depth(page)).toBe('1')
  })

  test('quick-insert drafts stay out of history until committed', async ({ page }) => {
    await insertSegments(page, 2)
    const before = await depth(page)

    await page.getByTestId('nav-voice-library').click()
    await page.getByTestId('voice-library-tab-segments').click()
    await page.getByRole('button', { name: 'Insert into Stitch Studio' }).nth(2).click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeVisible()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(3)

    // The draft surface has no history of its own, and must not offer the studio's.
    await expect(page.getByTestId('stitch-undo')).toHaveCount(0)
    await expect(page.getByTestId('stitch-redo')).toHaveCount(0)

    await page.getByTestId('stitch-clip').first().getByRole('button', { name: 'Remove clip' }).click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(2)
    await page.getByTestId('stitch-cancel-draft').click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeHidden()

    await page.getByTestId('nav-stitch-studio').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(2)
    expect(await depth(page), 'draft edits must not enter the committed plan history').toBe(before)

    // Committing is a plan change like any other: exactly one entry, and one undo returns
    // to the plan the draft was seeded from.
    await page.getByTestId('nav-voice-library').click()
    await page.getByTestId('voice-library-tab-segments').click()
    await page.getByRole('button', { name: 'Insert into Stitch Studio' }).nth(2).click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeVisible()
    await page.getByTestId('stitch-open-studio').click()
    await expect(page.getByTestId('stitch-editor-dialog')).toBeHidden()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(3)
    expect(await depth(page)).toBe(String(Number(before) + 1))

    await page.keyboard.press('ControlOrMeta+z')
    await expect(page.getByTestId('stitch-clip')).toHaveCount(2)
  })
})
