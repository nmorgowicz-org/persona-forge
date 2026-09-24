import { test, expect } from '@playwright/test'
import { collectLongTasks } from '../fixtures/longtasks.mjs'

// B-P7: motion as feedback. Motion here has one job -- telling you what just happened -- so the
// claims are about *when* things arrive, not about how they look:
//
//   1. a reordered clip travels to its new place instead of teleporting;
//   2. under reduced motion it arrives immediately, because the travel is decoration and the
//      position is the information;
//   3. dialogs and menus animate in rather than appearing;
//   4. none of it costs a long task.
//
// RED-first: test 1 must fail on unmodified code because the reorder teleports.

async function insertClips(page, n) {
  await page.goto('/')
  await page.getByTestId('nav-stitch-studio').click()
  await page.getByTestId('stitch-picker-toggle-segments').click()
  const items = page.getByTestId('stitch-picker-item-segments')
  await expect(items.first()).toBeVisible()
  for (let i = 0; i < n; i++) await items.nth(i).click()
  await page.getByTestId('stitch-picker-insert-segments').click()
  await expect(page.getByTestId('stitch-clip')).toHaveCount(n)
}

/**
 * Reorder the first clip to the right and record its x on every animation frame. Returns the
 * positions in order, starting with where it was before the click.
 */
async function reorderAndSample(page) {
  return page.evaluate(async () => {
    // The animated element is the wrapper (it carries `layout`); the reorder buttons live on
    // the Reorder.Item inside it.
    const wrapper = document.querySelector('[data-testid="stitch-clip-wrapper"]')
    if (!wrapper) return null
    const readX = () => wrapper.getBoundingClientRect().x
    // Not by title: the tooltip layer moves titles to `data-app-tooltip` at runtime.
    const moveRight = wrapper.querySelector('[data-testid="stitch-clip-move-right"]')
    if (!moveRight) return null

    const positions = [readX()]
    moveRight.click()
    for (let frame = 0; frame < 20; frame++) {
      await new Promise((resolve) => requestAnimationFrame(resolve))
      positions.push(readX())
    }
    return { positions, start: positions[0], end: positions[positions.length - 1] }
  })
}

test.describe('B-P7: motion as feedback', () => {
  test('a reordered clip travels to its new position instead of jumping', async ({ page }) => {
    await insertClips(page, 2)
    const result = await reorderAndSample(page)
    expect(result, 'no reorder buttons found').not.toBeNull()
    expect(result.end, `never moved: ${result.positions.join(', ')}`).toBeGreaterThan(result.start)

    // At least one frame lands strictly between the two ends: that is the difference between
    // an animated move and a teleport.
    const between = result.positions.filter((x) => x > result.start + 0.5 && x < result.end - 0.5)
    expect(between.length, `positions: ${result.positions.map((x) => x.toFixed(0)).join(', ')}`).toBeGreaterThan(0)
  })

  test('under reduced motion the same reorder arrives immediately', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await insertClips(page, 2)
    const result = await reorderAndSample(page)
    expect(result, 'no reorder buttons found').not.toBeNull()
    expect(result.end).toBeGreaterThan(result.start)
    // The position is the information; the travel is the decoration. With travel removed the
    // clip is never *between* the two positions -- it is at one or the other. (It still takes
    // React a frame to re-render, which is not travel.)
    const between = result.positions.filter((x) => x > result.start + 0.5 && x < result.end - 0.5)
    expect(between.length, `positions: ${result.positions.map((x) => x.toFixed(0)).join(', ')}`).toBe(0)
  })

  test('dialogs animate in rather than appearing', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()
    await page.getByTestId('stitch-picker-toggle-segments').click()

    const surface = page.locator('[data-state="open"]').first()
    await expect(surface).toBeVisible({ timeout: 15000 })
    // Either a CSS enter animation or a motion-driven style counts; what must not be true is
    // that the surface simply appears.
    const entering = await surface.evaluate((el) => {
      const style = getComputedStyle(el)
      return {
        animation: style.animationName,
        transform: style.transform,
        opacity: style.opacity,
      }
    })
    const hasEnter = entering.animation !== 'none' || entering.transform !== 'none' || Number(entering.opacity) < 1
    expect(hasEnter, `animation=${entering.animation} transform=${entering.transform} opacity=${entering.opacity}`).toBe(true)
  })

  test('a reorder stays inside the long-task budget', async ({ page }) => {
    await insertClips(page, 3)
    const result = await collectLongTasks(page, async () => {
      for (let move = 0; move < 4; move++) await reorderAndSample(page)
    })
    expect(result.supported, 'PerformanceObserver longtask is unavailable in this browser').toBe(true)
    expect(result.over, `long tasks: ${result.all.join(', ')} ms`).toEqual([])
  })
})
