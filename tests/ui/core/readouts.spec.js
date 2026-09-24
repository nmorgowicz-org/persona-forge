import { test, expect } from '@playwright/test'

// B-P8: readout typography and labeled controls (Plan A V3's residue absorbed).
//
// Two claims, both about whether a number or a dropdown says what it is:
//
//   1. every select on Speak, Voice Design and Voice Edit has a name that is *visible* on the
//      screen and is not merely the value it happens to hold ("English" is a language, not a
//      label; "Off" is a state, not a function);
//   2. time and level readouts are tabular and carry a unit, so a changing value does not
//      reflow the text around it and "520" is never mistaken for seconds. Enforced as a sweep
//      over the *shape* of the rendered text (a figure with a unit) rather than a list of
//      testids, so a new readout cannot quietly skip the role.
//
// RED-first: test 1 must fail on unmodified code because those selects have no label.

/** The accessible name, resolved the way a browser would: aria-label, then aria-labelledby,
 * then the element's own text. */
async function accessibleName(locator) {
  return locator.evaluate((el) => {
    const label = el.getAttribute('aria-label')
    if (label && label.trim()) return label.trim()
    const labelledBy = el.getAttribute('aria-labelledby')
    if (labelledBy) {
      const text = labelledBy
        .split(/\s+/)
        .map((id) => document.getElementById(id)?.textContent?.trim() ?? '')
        .join(' ')
        .trim()
      if (text) return text
    }
    // A native control wrapped in / pointed at by a <label for=...> takes its name from it --
    // NOT from its textContent, which for a <select> is the concatenation of every option.
    const native = el.labels
    if (native && native.length) {
      const text = Array.from(native)
        .map((node) => node.textContent?.trim() ?? '')
        .join(' ')
        .trim()
      if (text) return text
    }
    return (el.textContent ?? '').trim()
  })
}

/** Every visible micro-label on the page. */
async function visibleMicroLabels(page) {
  return page.locator('.micro-label').evaluateAll((els) =>
    els.filter((el) => el.getBoundingClientRect().width > 0).map((el) => (el.textContent ?? '').trim()),
  )
}

/** Returns how many selects were examined. A surface may legitimately have none (the OmniVoice
 * panel is all chips), so the caller asserts on the total instead -- a broken locator would
 * otherwise pass by finding nothing. */
async function assertEverySelectIsLabelled(page, surface) {
  const labels = await visibleMicroLabels(page)
  const selects = page.locator('select, [role="combobox"]')
  const count = await selects.count()

  const unlabelled = []
  let checked = 0
  for (let index = 0; index < count; index++) {
    const select = selects.nth(index)
    if (!(await select.isVisible())) continue
    checked++
    const name = await accessibleName(select)
    if (!labels.includes(name)) unlabelled.push(name || '(no name)')
  }
  expect(unlabelled, `${surface}: selects whose name is not a visible .micro-label: ${unlabelled.join(' | ')}`).toEqual([])
  return checked
}

test.describe('B-P8: readout typography and labeled controls', () => {
  test('every select on Speak, Voice Design and Voice Edit carries a visible label', async ({ page }) => {
    await page.goto('/')
    let checked = await assertEverySelectIsLabelled(page, 'Speak')

    await page.getByTestId('nav-voice-design').click()
    // The page opens on OmniVoice (the only accent-capable engine), which is all chips; the
    // Qwen panel has its own selects, so both engines are checked.
    await page.getByTestId('omnivoice-instruct').waitFor({ timeout: 15000 })
    checked += await assertEverySelectIsLabelled(page, 'Voice Design (OmniVoice)')
    await page.getByTestId('engine-qwen').click()
    await page.getByTestId('voice-design-description').waitFor({ timeout: 15000 })
    checked += await assertEverySelectIsLabelled(page, 'Voice Design (Qwen)')

    await page.getByTestId('nav-voice-edit').click()
    await expect(page.getByTestId('voice-edit-page')).toBeVisible({ timeout: 15000 })
    checked += await assertEverySelectIsLabelled(page, 'Voice Edit')

    // A broken locator must not pass by finding nothing.
    expect(checked, 'no selects were examined at all').toBeGreaterThanOrEqual(4)
  })

  test('the gap readout carries its unit', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()
    await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
    const items = page.getByTestId('stitch-picker-item-segments')
    await expect(items.first()).toBeVisible()
    for (let i = 0; i < 2; i++) await items.nth(i).click()
    await page.getByTestId('stitch-picker-insert-segments').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(2)

    const gap = page.getByTestId('stitch-gap-control').first()
    await expect(gap).toContainText(/\d+\s*ms/)
    // A bare number would be the same digits with no unit anywhere in the control.
    const text = (await gap.textContent()) ?? ''
    expect(text.replace(/\d+/g, ''), `gap control text: ${text}`).toMatch(/ms|s\b/)
  })

  test('no numeric readout anywhere is left non-tabular', async ({ page }) => {
    // The unit-bearing figure is the thing a readout is: a value with a unit. Asserting on the
    // shape of the rendered text (rather than a list of testids) means a new readout cannot
    // quietly skip the role, which is exactly how "1.0x" and "0ms" escaped it.
    const NUMERIC_READOUT = /^[+-]?\d+(?:\.\d+)?\s*(?:x|ms|s|Hz|kHz|dB|dBFS|LUFS|%)$/

    const offendersOn = async () =>
      page.locator('span, div, p, li').evaluateAll((els, source) => {
        const re = new RegExp(source)
        return els
          .filter((el) => el.children.length === 0 && re.test((el.textContent ?? '').trim()))
          .filter((el) => el.getBoundingClientRect().width > 0)
          // font-variant-numeric inherits, so a figure inside .readout passes honestly.
          .filter((el) => !getComputedStyle(el).fontVariantNumeric.includes('tabular-nums'))
          .map((el) => `${(el.textContent ?? '').trim()} [${getComputedStyle(el).fontVariantNumeric}]`)
      }, NUMERIC_READOUT.source)

    const check = async (surface) => {
      const offenders = await offendersOn()
      expect(offenders, `${surface}: readouts that are not tabular`).toEqual([])
    }

    await page.goto('/')
    await page.getByTestId('speak-text-input').fill('Readout sweep.')
    await page.getByTestId('speak-generate-button').click()
    await expect(page.getByTestId('speak-result')).toBeVisible({ timeout: 30000 })
    await check('Speak')

    await page.getByTestId('nav-voice-edit').click()
    await expect(page.getByTestId('voice-edit-page')).toBeVisible({ timeout: 15000 })
    await expect(page.getByTestId('voice-edit-save-variant')).toBeVisible({ timeout: 15000 })
    await check('Voice Edit')

    await page.getByTestId('nav-voice-library').click()
    await expect(page.getByTestId('voice-library-tab-voices')).toBeVisible({ timeout: 15000 })
    await check('Voice Library')

    // The timeline's own ruler and zoom readout are time readouts too.
    await page.getByTestId('nav-stitch-studio').click()
    await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
    const items = page.getByTestId('stitch-picker-item-segments')
    await expect(items.first()).toBeVisible()
    for (let i = 0; i < 2; i++) await items.nth(i).click()
    await page.getByTestId('stitch-picker-insert-segments').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(2)
    await check('Stitch Studio')
  })

  test('time and level readouts are tabular and carry a unit', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('speak-text-input').fill('Readout check.')
    await page.getByTestId('speak-generate-button').click()
    await expect(page.getByTestId('speak-result')).toBeVisible({ timeout: 30000 })

    for (const testId of ['deck-peak-readout', 'deck-lufs-readout']) {
      const el = page.getByTestId(testId)
      await expect(el).toBeVisible({ timeout: 20000 })
      const style = await el.evaluate((node) => getComputedStyle(node).fontVariantNumeric)
      expect(style, `${testId} is not tabular`).toContain('tabular-nums')
      await expect(el, `${testId} has no unit`).toContainText(/dBFS|LUFS|dB/)
    }

    // The meter's live readout is the one that changes every frame; it is the readout that
    // most needs figures that do not move. (`[role="meter"]` is the track, so its row is where
    // the readout lives -- the label beside it is deliberately not tabular.)
    const meterRow = page.locator('[role="meter"]').first().locator('xpath=..')
    const meterReadout = meterRow.locator('.readout')
    await expect(meterReadout).toHaveCount(1)
    const meterStyle = await meterReadout.evaluate((node) => getComputedStyle(node).fontVariantNumeric)
    expect(meterStyle, 'the meter readout is not tabular').toContain('tabular-nums')
  })
})
