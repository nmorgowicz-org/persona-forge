import { test, expect } from '@playwright/test'

// A-1 (S1 + N1 + N2): drag-scrub, click-to-type, double-click reset, and wheel adjust on the
// stitch numeric controls, plus deck playback speed. RED-first: every test must fail on
// unmodified code because the feature is missing, then pass after the useDragScrubValue
// migration. Plan: docs/plans/20260922-premium_audio_plugin_ux.md S1, N1, N2; runbook card A-1.

async function insertSegments(page, n) {
  await page.goto('/')
  await page.getByTestId('nav-stitch-studio').click()
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
  // Trim/fade steppers clamp to the analyzed audio duration (max stays 0 until the clip's
  // audio analysis lands); the trim handles only render once it has, so they are the
  // readiness signal for the steppers being actually adjustable.
  await expect(page.getByTestId('stitch-trim-handle-left').first()).toBeVisible()
}

function rowOf(locator) {
  return locator.locator('xpath=ancestor::div[1]')
}

function clipIds(page) {
  return page.getByTestId('stitch-clip').evaluateAll((els) => els.map((el) => el.dataset.clipId))
}

test.describe('drag-scrub numeric controls (A-1: S1, N1, N2)', () => {
  test('horizontal drag scrubs trim start; Shift drags by less', async ({ page }) => {
    await insertSegments(page, 1)
    await openFirstClipEditor(page)
    const stepper = page.getByTestId('stitch-stepper-trim-start-value').first()
    const idsBefore = await clipIds(page)

    const box = await stepper.boundingBox()
    const y = box.y + box.height / 2
    await page.mouse.move(box.x + box.width / 2, y)
    await page.mouse.down()
    await page.mouse.move(box.x + box.width / 2 + 40, y, { steps: 4 })
    await page.mouse.up()
    const coarse = Number(await stepper.textContent())
    expect(coarse).toBeGreaterThan(0)

    // The scrub gesture must never leak into the clip reorder drag.
    expect(await clipIds(page)).toEqual(idsBefore)

    // Trimming changes the clip's effective width, so recapture the position before the
    // second gesture (same discipline as the trim-drag test in studio.spec.js).
    const box2 = await stepper.boundingBox()
    const y2 = box2.y + box2.height / 2
    await page.keyboard.down('Shift')
    await page.mouse.move(box2.x + box2.width / 2, y2)
    await page.mouse.down()
    await page.mouse.move(box2.x + box2.width / 2 + 40, y2, { steps: 4 })
    await page.mouse.up()
    await page.keyboard.up('Shift')
    const fine = Number(await stepper.textContent())
    expect(fine).toBeGreaterThan(coarse)
    expect(fine - coarse).toBeLessThan(coarse)
    expect(await clipIds(page)).toEqual(idsBefore)
  })

  test('click-to-type accepts 0.2s as 200 ms; Escape cancels the edit', async ({ page }) => {
    await insertSegments(page, 1)
    await openFirstClipEditor(page)
    const stepper = page.getByTestId('stitch-stepper-fade-in-value').first()
    const row = rowOf(stepper)

    await stepper.click()
    const input = row.getByRole('textbox')
    await expect(input).toBeVisible()
    await input.fill('0.2s')
    await input.press('Enter')
    await expect(stepper).toHaveText('200')

    await stepper.click()
    const input2 = row.getByRole('textbox')
    await input2.fill('0.9s')
    await input2.press('Escape')
    await expect(stepper).toHaveText('200')
  })

  test('double-click on the control row restores the trim default (0 ms)', async ({ page }) => {
    await insertSegments(page, 1)
    await openFirstClipEditor(page)
    const stepper = page.getByTestId('stitch-stepper-trim-start-value').first()
    const increase = page.getByRole('button', { name: 'Increase Trim start' })
    for (let i = 0; i < 4; i++) await increase.click()
    await expect(stepper).toHaveText('40')

    // The reset gesture targets the control's label/row area, not the value itself: the
    // value's single click opens the typed-entry editor, which replaces the value before a
    // second click could land on it.
    const row = rowOf(stepper)
    const rowBox = await row.boundingBox()
    await row.dblclick({ position: { x: 8, y: rowBox.height / 2 } })
    await expect(stepper).toHaveText('0')
  })

  test('wheel nudges the stepper; Ctrl+wheel over the timeline still zooms', async ({ page }) => {
    await insertSegments(page, 3)
    await openFirstClipEditor(page)
    const stepper = page.getByTestId('stitch-stepper-trim-start-value').first()
    const box = await stepper.boundingBox()
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await page.mouse.wheel(0, -100)
    await expect(stepper).toHaveText('10')
    await page.mouse.wheel(0, 100)
    await expect(stepper).toHaveText('0')

    // The existing timeline zoom behavior is unchanged by the wheel migration. Three
    // clips keep auto-Fit below the 400px/s clamp, so a zoom step must visibly change it.
    const zoomBefore = await page.getByTestId('stitch-zoom-level').textContent()
    const ruler = page.getByTestId('stitch-ruler-tick').first()
    const rulerBox = await ruler.boundingBox()
    await page.keyboard.down('Control')
    await page.mouse.move(rulerBox.x + rulerBox.width / 2, rulerBox.y + rulerBox.height / 2)
    await page.mouse.wheel(0, -100)
    await page.keyboard.up('Control')
    await expect(page.getByTestId('stitch-zoom-level')).not.toHaveText(zoomBefore)
  })

  test('deck speed: drag adjusts the rate; double-click resets to 1.0', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('speak-text-input').fill('Speed scrub check.')
    await page.getByTestId('speak-generate-button').click()
    await expect(page.getByTestId('speak-result')).toBeVisible({ timeout: 30000 })
    const deck = page.getByTestId('deck-speed')
    await expect(deck).toBeVisible()

    const box = await deck.boundingBox()
    const y = box.y + box.height / 2
    await page.mouse.move(box.x + box.width / 2, y)
    await page.mouse.down()
    await page.mouse.move(box.x + box.width / 2 + 40, y, { steps: 4 })
    await page.mouse.up()
    await expect(deck).toHaveAttribute('data-speed', '1.4')

    // Reset targets the container, not the value: the value's click opens the editor.
    await deck.dblclick({ position: { x: 4, y: y - box.y } })
    await expect(deck).toHaveAttribute('data-speed', '1')
  })
})
