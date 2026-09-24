// A-2 (S2): cursor-anchored Ctrl-wheel zoom and hover time guide. RED-first: every test
// must fail on unmodified code (wheel zoom currently zooms around the scroll origin, no
// hover guide exists), then pass after the GREEN implementation. Plan:
// docs/plans/20260922-premium_audio_plugin_ux.md S2; runbook card A-2.
//
// Invariance measurement: a ruler tick is a fixed point of the arrangement. Its viewport
// x = contentX(pps) - scrollLeft. If the time under the pointer is preserved, then for the
// tick at pointer-time t: viewportX_after == viewportX_before (within 1px, per the card).
import { test, expect } from '@playwright/test'
import { suppressUpdateBanner } from '../fixtures/pointer.mjs'

/**
 * The fitted zoom level once it has stopped moving.
 *
 * Fit derives its px/s from the plan's total duration, and the plan keeps growing while the
 * clip analysis resolves -- so a level sampled before that settles is not comparable to one
 * sampled after. This is why the test below would occasionally read 109px/s and then find
 * 106px/s restored: the plan was still 3% short when it took the first reading. Two identical
 * readings in a row is the same "settled" idiom `settledBox` uses for geometry.
 */
async function settledZoomLevel(page, { attempts = 60, intervalMs = 100 } = {}) {
  const level = page.getByTestId('stitch-zoom-level')
  let previous = null
  for (let attempt = 0; attempt < attempts; attempt++) {
    const text = await level.textContent()
    if (text && text === previous) return text
    previous = text
    await page.waitForTimeout(intervalMs)
  }
  return previous
}

test.describe('A-2: cursor-anchored zoom and hover time guide', () => {
  test.beforeEach(async ({ page }) => {
    // Preventive, not this test's cause (see `settledZoomLevel`): the update banner inserts
    // itself above the content five seconds after startup and changes the container width, the
    // same race P7 hit in the drag specs. This spec finishes inside that window today, which is
    // exactly the kind of timing that stops being true on a slower machine.
    await suppressUpdateBanner(page)
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()
    await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
    const items = page.getByTestId('stitch-picker-item-segments')
    await expect(items.first()).toBeVisible()
    for (let i = 0; i < 3; i++) await items.nth(i).click()
    await page.getByTestId('stitch-picker-insert-segments').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(3)
  })

  test('Ctrl-wheel zoom keeps the time under the pointer fixed (zoom in and out)', async ({ page }) => {
    // The pointer-time invariant needs two things: real scroll slack (content wider than
    // the viewport, so the correction has somewhere to go) and pps headroom below the
    // 400px/s clamp (so the wheel still changes the scale in both directions). At Fit the
    // content exactly fills the viewport, so zoom IN from Fit until there is slack,
    // stopping below the clamp. The ruler box is captured afterwards: zooming resizes it.
    for (let i = 0; i < 8; i++) {
      const state = await page.evaluate(() => {
        const ruler = document.querySelector('[data-testid="stitch-timeline-ruler"]')
        const scroll = ruler.closest('.overflow-x-auto')
        return { slack: scroll.scrollWidth - scroll.clientWidth, pps: Number(document.querySelector('[data-testid="stitch-zoom-level"]').textContent) }
      })
      if (state.slack > 150 && state.pps < 300) break
      await page.getByTestId('stitch-zoom-in').click()
    }
    const ruler = page.getByTestId('stitch-timeline-ruler')
    const rulerBox = await ruler.boundingBox()
    for (const deltaY of [-120, 120, -120]) {
      const pointerX = rulerBox.x + rulerBox.width * 0.7
      const pointerY = rulerBox.y + rulerBox.height / 2

      // Snapshot the viewport x of the ruler tick whose seconds are closest to the
      // pointer time, and the scrollLeft, before the zoom.
      const before = await page.evaluate(() => {
        const ticks = [...document.querySelectorAll('[data-testid="stitch-ruler-tick"]')]
        const ruler = document.querySelector('[data-testid="stitch-timeline-ruler"]')
        const rect = ruler.getBoundingClientRect()
        const scroll = ruler.closest('.overflow-x-auto')
        const pps = ticks.length > 1 ? (ticks[1].getBoundingClientRect().left - ticks[0].getBoundingClientRect().left) / (Number(ticks[1].dataset.seconds) - Number(ticks[0].dataset.seconds)) : 1
        return { ticks: ticks.map((t) => ({ s: Number(t.dataset.seconds), x: t.getBoundingClientRect().left })), scrollLeft: scroll.scrollLeft, pps, rulerX: rect.left, rulerW: rect.width }
      })
      const pointerTime = ((pointerX - before.rulerX) / before.rulerW) * 0 + (pointerX - before.rulerX) / before.pps
      const nearest = before.ticks.reduce((a, b) => Math.abs(b.s - pointerTime) < Math.abs(a.s - pointerTime) ? b : a)
      const viewportXBefore = nearest.x

      await page.keyboard.down('Control')
      await page.mouse.move(pointerX, pointerY)
      await page.mouse.wheel(0, deltaY)
      await page.keyboard.up('Control')
      await page.waitForTimeout(150)

      const after = await page.evaluate((tickSeconds) => {
        const ticks = [...document.querySelectorAll('[data-testid="stitch-ruler-tick"]')]
        const t = ticks.find((el) => Number(el.dataset.seconds) === tickSeconds)
        return t ? t.getBoundingClientRect().left : null
      }, nearest.s)

      expect(after, `tick at ${nearest.s}s must stay at the same viewport x`).not.toBeNull()
      // ±1px per the card ("± 1 px of ruler mapping").
      expect(Math.abs(after - viewportXBefore)).toBeLessThanOrEqual(1)
    }
  })

  test('hovering the ruler shows a time guide that follows the pointer and hides on leave', async ({ page }) => {
    const ruler = page.getByTestId('stitch-timeline-ruler')
    const box = await ruler.boundingBox()
    const y = box.y + box.height / 2

    // No guide before hovering.
    await expect(page.getByTestId('timeline-hover-guide')).toBeHidden()

    // Hover near 1/4 of the ruler.
    await page.mouse.move(box.x + box.width * 0.25, y)
    const guide = page.getByTestId('timeline-hover-guide')
    await expect(guide).toBeVisible()
    const labelA = await guide.textContent()
    expect(labelA).toMatch(/\d/)

    // The guide must track the pointer: a different x must update the label (time increases).
    await page.mouse.move(box.x + box.width * 0.75, y)
    await expect(guide).toBeVisible()
    const labelB = await guide.textContent()
    expect(labelB).not.toBe(labelA)

    // Leaving the timeline hides the guide.
    await page.mouse.move(box.x - 80, box.y - 80)
    await expect(page.getByTestId('timeline-hover-guide')).toBeHidden()
  })

  test('zoom Fit still restores auto-fit after manual zoom', async ({ page }) => {
    const fitLevel = await settledZoomLevel(page)
    // Zoom OUT from Fit: three clips fit near ~400px/s (the clamp), so 1.25x zoom-in
    // would saturate at MAX_PPS and the level would never change. Zooming out goes
    // below the clamp and Fit must restore the exact original level.
    await page.getByTestId('stitch-zoom-out').click()
    await expect(page.getByTestId('stitch-zoom-level')).not.toHaveText(fitLevel)
    await page.getByTestId('stitch-zoom-fit').click()
    await expect(page.getByTestId('stitch-zoom-level')).toHaveText(fitLevel)
  })
})
