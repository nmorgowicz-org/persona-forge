import { test, expect } from '@playwright/test'

// A-3 (S3 + S4): pointer-safe waveform gestures on the Speak result deck, and one shared
// numeric grammar (units, tab order, focus ring) across the trim / fade / gap controls.
// RED-first: every test must fail on unmodified code because the feature is missing, then
// pass after the Waveform pointer-event migration and the shared ms-format helper.
// Plan: docs/archive/luminous-instrument/20260922-premium_audio_plugin_ux.md S3 + S4; runbook card A-3.

async function generateResult(page) {
  await page.goto('/')
  await page.getByTestId('speak-text-input').fill('Pointer-safe waveform gesture test.')
  await page.getByTestId('speak-generate-button').click()
  await expect(page.getByTestId('speak-result')).toBeVisible({ timeout: 30000 })
  const audio = page.getByTestId('speak-result').locator('audio')
  await expect(audio).toHaveCount(1)
  // Wait for metadata so the deck knows its duration (and can map fractions to times).
  await audio.evaluate(async (el) => {
    if (el.readyState < 1) await new Promise((r) => el.addEventListener('loadedmetadata', r, { once: true }))
  })
  return audio
}

async function insertSegments(page, n) {
  await page.goto('/')
  await page.getByTestId('nav-stitch-studio').click()
  await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
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

/** The three numeric controls share one grammar: `data-numeric-control` names the control
 * (trim / fade / gap) and the value element carries the bare number while a sibling unit
 * element carries the unit. */
function controlRow(page, name) {
  return page.locator(`[data-numeric-control="${name}"]`).first()
}

test.describe('A-3: pointer-safe waveform and one numeric grammar', () => {
  test('a pointer drag that leaves the waveform keeps selecting; a click still seeks', async ({ page }) => {
    const audio = await generateResult(page)
    const waveform = page.getByTestId('deck-waveform')
    await expect(waveform).toBeVisible()
    const box = await waveform.boundingBox()
    const midY = box.y + box.height / 2
    const xAt = (frac) => box.x + box.width * frac

    // A drag that wanders off the control mid-gesture must keep tracking the pointer and
    // must still commit on release: the gesture is owned by the waveform (pointer capture),
    // not by whatever happens to be under the pointer. Releasing outside the control is the
    // discriminating case -- an uncaptured gesture never sees that pointerup at all.
    await page.mouse.move(xAt(0.25), midY)
    await page.mouse.down()
    await page.mouse.move(xAt(0.25), box.y + box.height + 60, { steps: 4 })
    await page.mouse.move(xAt(0.75), box.y + box.height + 60, { steps: 4 })
    await page.mouse.up()

    const band = page.getByTestId('deck-waveform-selection')
    await expect(band).toBeVisible()
    const geometry = await band.evaluate((el) => ({ left: parseFloat(el.style.left), width: parseFloat(el.style.width) }))
    expect(Math.abs(geometry.left - 25)).toBeLessThanOrEqual(2)
    expect(Math.abs(geometry.width - 50)).toBeLessThanOrEqual(3)

    // The selected slice is what gets auditioned, so playback restarts at its start.
    const state = await audio.evaluate((el) => ({ currentTime: el.currentTime, duration: el.duration, paused: el.paused }))
    expect(state.currentTime).toBeGreaterThanOrEqual(state.duration * 0.25 - 0.35)
    expect(state.currentTime).toBeLessThanOrEqual(state.duration * 0.25 + 0.35)

    // A click without movement is still a plain seek, and it clears the slice.
    await audio.evaluate((el) => el.pause())
    await page.mouse.click(xAt(0.6), midY)
    await expect(band).toHaveCount(0)
    const sought = await audio.evaluate((el) => ({ currentTime: el.currentTime, duration: el.duration }))
    expect(Math.abs(sought.currentTime - sought.duration * 0.6)).toBeLessThanOrEqual(0.2)
  })

  test('trim, fade, and gap show units the same way and accept ms and s input', async ({ page }) => {
    await insertSegments(page, 2)
    await openFirstClipEditor(page)

    const trim = page.getByTestId('stitch-stepper-trim-start-value').first()
    const fade = page.getByTestId('stitch-stepper-fade-in-value').first()
    const gap = page.getByTestId('stitch-gap-control').first()

    // Below one second every control shows the bare number with an `ms` unit.
    const trimRow = trim.locator('xpath=ancestor::div[1]')
    await trim.click()
    await trimRow.getByRole('textbox').fill('200ms')
    await trimRow.getByRole('textbox').press('Enter')
    await expect(trim).toHaveText('200')
    await expect(controlRow(page, 'trim').getByTestId('stitch-stepper-trim-start-value-unit')).toHaveText('ms')

    const fadeRow = fade.locator('xpath=ancestor::div[1]')
    await fade.click()
    await fadeRow.getByRole('textbox').fill('0.5s')
    await fadeRow.getByRole('textbox').press('Enter')
    await expect(fade).toHaveText('500')
    await expect(controlRow(page, 'fade').getByTestId('stitch-stepper-fade-in-value-unit')).toHaveText('ms')

    // Seconds are accepted on input and shown as seconds once the value reaches 1000 ms.
    await trim.click()
    await trimRow.getByRole('textbox').fill('1.2s')
    await trimRow.getByRole('textbox').press('Enter')
    await expect(trim).toHaveText('1.2')
    await expect(controlRow(page, 'trim').getByTestId('stitch-stepper-trim-start-value-unit')).toHaveText('s')

    await fade.click()
    await fadeRow.getByRole('textbox').fill('1s')
    await fadeRow.getByRole('textbox').press('Enter')
    await expect(fade).toHaveText('1')
    await expect(controlRow(page, 'fade').getByTestId('stitch-stepper-fade-in-value-unit')).toHaveText('s')

    // The gap control follows the same grammar, both ways.
    await gap.getByRole('button').first().click()
    const gapInput = gap.getByRole('textbox')
    await gapInput.fill('1.5s')
    await gapInput.press('Enter')
    await expect(gap.getByTestId('stitch-gap-value')).toHaveText('1.5')
    await expect(gap.getByTestId('stitch-gap-unit')).toHaveText('s')

    await gap.getByTestId('stitch-gap-value').click()
    await gap.getByRole('textbox').fill('250ms')
    await gap.getByRole('textbox').press('Enter')
    await expect(gap.getByTestId('stitch-gap-value')).toHaveText('250')
    await expect(gap.getByTestId('stitch-gap-unit')).toHaveText('ms')
  })

  test('tab order walks trim then fade then gap, each with the same focus ring', async ({ page }) => {
    await insertSegments(page, 2)
    await openFirstClipEditor(page)

    // Walk forward from the trim control and record which numeric control each stop
    // belongs to, plus the ring the control paints while it holds keyboard focus. The
    // trim/fade pairs (start/end, in/out) are consecutive stops of the same control, so
    // repeated names collapse: the sequence is trim -> fade -> gap.
    await page.getByTestId('stitch-stepper-trim-start-value-row').first().focus()
    const stops = []
    const rings = new Map()
    for (let i = 0; i < 40; i++) {
      await page.keyboard.press('Tab')
      const stop = await page.evaluate(() => {
        const el = document.activeElement
        const control = el?.closest('[data-numeric-control]')
        if (!control) return null
        return { name: control.getAttribute('data-numeric-control'), shadow: getComputedStyle(control).boxShadow }
      })
      if (!stop) continue
      if (!rings.has(stop.name)) rings.set(stop.name, stop.shadow)
      if (stops[stops.length - 1] !== stop.name) stops.push(stop.name)
      if (stops.length >= 3) break
    }
    expect(stops).toEqual(['trim', 'fade', 'gap'])

    // Every control paints the same focus ring while it holds keyboard focus. Anything the
    // forward walk did not reach is picked up on the way back.
    for (let i = 0; i < 40 && rings.size < 3; i++) {
      await page.keyboard.press('Shift+Tab')
      const stop = await page.evaluate(() => {
        const control = document.activeElement?.closest('[data-numeric-control]')
        if (!control) return null
        return { name: control.getAttribute('data-numeric-control'), shadow: getComputedStyle(control).boxShadow }
      })
      if (stop && !rings.has(stop.name)) rings.set(stop.name, stop.shadow)
    }
    const shadows = ['trim', 'fade', 'gap'].map((name) => rings.get(name))
    for (const shadow of shadows) {
      expect(shadow).toBeTruthy()
      expect(shadow).not.toBe('none')
      expect(shadow).toBe(shadows[0])
    }
  })
})

// A-3b (S3 completion): one hover time readout on every waveform surface, and the
// modifier-held scrub. RED-first: on the pre-card code the deck and the clip lane have no
// readout at all, the three existing readouts use three different precisions
// (2dp / 3dp / 2dp), and no scrub gesture exists. Owner decision: the readout shows 10 ms
// everywhere, at any zoom (a readout is a single value, so it need not share the coarser
// precision the ruler uses to keep tick labels from colliding). The readout must be written straight to
// the DOM -- pointer movement may not re-render a waveform that is hosting a gesture.
const SUB_SECOND_READOUT = /^\d+\.\d\ds$/ // 10 ms, below ten seconds

test.describe('A-3b: hover time readout and modifier scrub', () => {
  test('the deck shows the time under the pointer and hides it on leave', async ({ page }) => {
    const audio = await generateResult(page)
    const duration = await audio.evaluate((el) => el.duration)
    const waveform = page.getByTestId('deck-waveform')
    const readout = page.getByTestId('deck-waveform-time')
    await expect(readout).toBeHidden()

    const box = await waveform.boundingBox()
    const labelAt = async (fraction) => {
      await page.mouse.move(box.x + box.width * fraction, box.y + box.height / 2)
      await expect(readout).toBeVisible()
      return (await readout.textContent()) ?? ''
    }

    // The readout is the exact time under the pointer, in the ruler's grammar.
    expect(await labelAt(0.5)).toBe(`${(duration * 0.5).toFixed(2)}s`)
    const near = Number((await labelAt(0.25)).replace('s', ''))
    const far = Number((await labelAt(0.75)).replace('s', ''))
    expect(far).toBeGreaterThan(near)

    await page.mouse.move(box.x - 120, box.y - 120)
    await expect(readout).toBeHidden()
  })

  test('Alt-drag scrubs the deck playhead without touching the selected slice', async ({ page }) => {
    const audio = await generateResult(page)
    const duration = await audio.evaluate((el) => el.duration)
    await audio.evaluate((el) => el.pause())
    const waveform = page.getByTestId('deck-waveform')
    const box = await waveform.boundingBox()
    const y = box.y + box.height / 2

    await page.keyboard.down('Alt')
    await page.mouse.move(box.x + box.width * 0.2, y)
    await page.mouse.down()
    await page.mouse.move(box.x + box.width * 0.7, y, { steps: 5 })
    await page.mouse.up()
    await page.keyboard.up('Alt')

    const after = await audio.evaluate((el) => ({ currentTime: el.currentTime, paused: el.paused }))
    expect(Math.abs(after.currentTime - duration * 0.7)).toBeLessThanOrEqual(0.2)
    // A scrub only moves the playhead: it must not select a slice or start playback.
    expect(after.paused).toBe(true)
    await expect(page.getByTestId('deck-waveform-selection')).toHaveCount(0)
  })

  test('every waveform surface reads out time in the ruler\'s grammar', async ({ page }) => {
    // Deck (Speak result) and, on the same page load, the stitch clip lane plus the timeline
    // ruler that A-2 added -- three surfaces, one grammar.
    const audio = await generateResult(page)
    const duration = await audio.evaluate((el) => el.duration)
    const waveform = page.getByTestId('deck-waveform')
    const deckBox = await waveform.boundingBox()
    await page.mouse.move(deckBox.x + deckBox.width * 0.5, deckBox.y + deckBox.height / 2)
    const deckLabel = (await page.getByTestId('deck-waveform-time').textContent()) ?? ''
    expect(deckLabel).toBe(`${(duration * 0.5).toFixed(2)}s`)
    expect(deckLabel).toMatch(SUB_SECOND_READOUT)

    await insertSegments(page, 2)
    await expect(page.getByTestId('stitch-trim-handle-left').first()).toBeVisible()

    const lane = page.getByTestId('stitch-lane-time').first()
    const laneBox = await (await lane.evaluateHandle((el) => el.parentElement)).asElement().boundingBox()
    await page.mouse.move(laneBox.x + laneBox.width * 0.5, laneBox.y + laneBox.height / 2)
    const laneLabel = (await lane.textContent()) ?? ''
    expect(laneLabel).toMatch(SUB_SECOND_READOUT)

    const rulerGuide = page.getByTestId('timeline-hover-guide')
    const ruler = page.getByTestId('stitch-timeline-ruler')
    const rulerBox = await ruler.boundingBox()
    await page.mouse.move(rulerBox.x + rulerBox.width * 0.25, rulerBox.y + rulerBox.height / 2)
    await expect(rulerGuide).toBeVisible()
    const rulerLabel = (await rulerGuide.textContent()) ?? ''
    expect(rulerLabel).toMatch(SUB_SECOND_READOUT)

    // Same grammar means the same precision: no surface may drift to its own decimal count.
    expect(laneLabel.replace(/[\d.]/g, '')).toBe(deckLabel.replace(/[\d.]/g, ''))
    expect(rulerLabel.replace(/[\d.]/g, '')).toBe(deckLabel.replace(/[\d.]/g, ''))
  })
})
