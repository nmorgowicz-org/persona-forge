import { test, expect } from '@playwright/test'

// B-P5: the knob and fader instrument controls. This is the A-1 drag-scrub contract re-run
// against a new form -- vertical drag, Shift for fine, double-click reset, wheel nudge,
// click-to-type, arrow keys, and a slider role -- plus the one thing a knob has that a numeric
// field does not: a value bubble you can read while you are dragging.
//
// RED-first: every test must fail on unmodified code because the control does not exist.

async function openDsp(page) {
  await page.goto('/')
  await page.getByTestId('nav-stitch-studio').click()
  await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
  const items = page.getByTestId('stitch-picker-item-segments')
  await expect(items.first()).toBeVisible()
  for (let i = 0; i < 2; i++) await items.nth(i).click()
  await page.getByTestId('stitch-picker-insert-segments').click()
  await expect(page.getByTestId('stitch-clip')).toHaveCount(2)
  await page.getByRole('button', { name: 'DSP controls' }).click()
  await expect(page.getByTestId('dsp-knob-crossfade')).toBeVisible()
  await settledBox(page.getByTestId('dsp-knob-crossfade'))
}

const valueOf = async (page, testId) => Number(await page.getByTestId(testId).getAttribute('aria-valuenow'))

/** The DSP panel animates open, so a box measured during the animation is already stale by the
 * time the pointer goes down and the drag reads as no travel at all. Wait for the box to stop
 * moving before dragging. */
async function settledBox(locator) {
  let previous = null
  for (let attempt = 0; attempt < 40; attempt++) {
    const box = await locator.boundingBox()
    if (box && previous && Math.abs(box.y - previous.y) < 0.5 && Math.abs(box.height - previous.height) < 0.5) {
      return box
    }
    previous = box
    await locator.page().waitForTimeout(50)
  }
  return previous
}

async function dragVertically(page, testId, pixels, modifiers = []) {
  const box = await settledBox(page.getByTestId(testId))
  if (!box) throw new Error(`${testId} has no box`)
  const x = box.x + box.width / 2
  const y = box.y + box.height / 2
  await page.mouse.move(x, y)
  for (const key of modifiers) await page.keyboard.down(key)
  await page.mouse.down()
  // Several small steps: a single jump can land before the drag threshold is crossed.
  for (let step = 1; step <= 6; step++) {
    await page.mouse.move(x, y - (pixels * step) / 6)
    await page.waitForTimeout(20)
  }
  await page.mouse.up()
  for (const key of modifiers) await page.keyboard.up(key)
}

test.describe('B-P5: knob and fader controls', () => {
  test('vertical drag changes the value, and Shift is finer', async ({ page }) => {
    await openDsp(page)
    const before = await valueOf(page, 'dsp-knob-crossfade')

    await dragVertically(page, 'dsp-knob-crossfade', 60)
    const coarse = await valueOf(page, 'dsp-knob-crossfade')
    expect(coarse, `before=${before} after=${coarse}`).toBeGreaterThan(before)

    // Reset, then repeat with Shift held: same travel, smaller change.
    await page.getByTestId('dsp-knob-crossfade').dblclick()
    const reset = await valueOf(page, 'dsp-knob-crossfade')
    await dragVertically(page, 'dsp-knob-crossfade', 60, ['Shift'])
    const fine = await valueOf(page, 'dsp-knob-crossfade')
    expect(fine - reset, `coarse=${coarse - before} fine=${fine - reset}`).toBeLessThan(coarse - before)
  })

  test('double-click resets to the plan default', async ({ page }) => {
    await openDsp(page)
    await dragVertically(page, 'dsp-knob-crossfade', 80)
    expect(await valueOf(page, 'dsp-knob-crossfade')).not.toBe(100)
    await page.getByTestId('dsp-knob-crossfade').dblclick()
    expect(await valueOf(page, 'dsp-knob-crossfade')).toBe(100)
  })

  test('wheel nudges the value by one step', async ({ page }) => {
    await openDsp(page)
    const before = await valueOf(page, 'dsp-knob-crossfade')
    const box = await settledBox(page.getByTestId('dsp-knob-crossfade'))
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await page.mouse.wheel(0, -120)
    await expect.poll(() => valueOf(page, 'dsp-knob-crossfade')).toBe(before + 5)
    await page.mouse.wheel(0, 120)
    await expect.poll(() => valueOf(page, 'dsp-knob-crossfade')).toBe(before)
  })

  test('clicking the value opens a typed entry', async ({ page }) => {
    await openDsp(page)
    const knob = page.getByTestId('dsp-knob-crossfade')
    await knob.getByRole('button', { name: /Crossfade/ }).click()
    const input = knob.getByRole('textbox')
    await expect(input).toBeVisible()
    await input.fill('250')
    await input.press('Enter')
    await expect.poll(() => valueOf(page, 'dsp-knob-crossfade')).toBe(250)
  })

  test('arrow keys step the value, and it is a slider to assistive tech', async ({ page }) => {
    await openDsp(page)
    const knob = page.getByTestId('dsp-knob-crossfade')
    await expect(knob).toHaveAttribute('role', 'slider')
    await expect(knob).toHaveAttribute('aria-valuemin', '0')
    await expect(knob).toHaveAttribute('aria-valuemax', '400')

    const before = await valueOf(page, 'dsp-knob-crossfade')
    await knob.focus()
    await page.keyboard.press('ArrowUp')
    await expect.poll(() => valueOf(page, 'dsp-knob-crossfade')).toBe(before + 5)
    await page.keyboard.press('ArrowDown')
    await expect.poll(() => valueOf(page, 'dsp-knob-crossfade')).toBe(before)
    // Shift is the coarse step, matching every other numeric control in the app.
    await page.keyboard.down('Shift')
    await page.keyboard.press('ArrowUp')
    await page.keyboard.up('Shift')
    await expect.poll(() => valueOf(page, 'dsp-knob-crossfade')).toBe(before + 25)
  })

  test('the value bubble is readable while dragging', async ({ page }) => {
    await openDsp(page)
    const knob = page.getByTestId('dsp-knob-crossfade')
    const bubble = knob.getByTestId('knob-bubble')
    await expect(bubble).toBeHidden()

    const box = await settledBox(knob)
    const x = box.x + box.width / 2
    const y = box.y + box.height / 2
    await page.mouse.move(x, y)
    await page.mouse.down()
    await page.mouse.move(x, y - 40)
    await expect(bubble).toBeVisible()
    await expect(bubble).toHaveText(/ms/)
    await page.mouse.up()
    // The bubble also shows on hover, so the pointer has to leave before it is gone.
    await page.mouse.move(0, 0)
    await expect(bubble).toBeHidden()
  })
})
