/**
 * A bounding box that has stopped moving, and is on screen.
 *
 * Two ways a measured box turns into a gesture that silently does nothing, both seen for real:
 *
 * 1. Several panels animate open (motion's height animation). `boundingBox()` returns a real box
 *    while that is still running, so a pointer gesture started from those coordinates lands
 *    somewhere else -- in one investigation, on the page background.
 * 2. The box is below the fold. `page.mouse` dispatches raw input: it performs no actionability
 *    checks and never scrolls, so coordinates outside the viewport reach no element at all. This
 *    is how the stitch scrub specs passed locally and failed on CI, whose viewport is 720px tall
 *    and where the clip panel sat below it -- the drag landed on nothing and the value stayed 0.
 *
 * Scrolling first puts the target where its coordinates mean something; waiting for two identical
 * measurements in a row handles the animation. Both are cheap and the caller cannot forget them.
 */
export async function settledBox(locator, { attempts = 40, intervalMs = 50 } = {}) {
  await locator.scrollIntoViewIfNeeded()
  let previous = null
  for (let attempt = 0; attempt < attempts; attempt++) {
    const box = await locator.boundingBox()
    if (
      box &&
      previous &&
      Math.abs(box.y - previous.y) < 0.5 &&
      Math.abs(box.height - previous.height) < 0.5 &&
      Math.abs(box.x - previous.x) < 0.5
    ) {
      return box
    }
    previous = box
    await locator.page().waitForTimeout(intervalMs)
  }
  return previous
}

/**
 * Keep the update banner out of the page.
 *
 * `UpdateAvailableBanner` waits 5 seconds after startup (deliberately, to avoid competing with
 * the first health poll) and then inserts itself above the content, pushing everything below it
 * down. Any test that measures a box before those 5 seconds and clicks after them aims at where
 * the element *was* -- which is how a drag ends up landing on the page background. The banner
 * has nothing to do with what these specs measure, so dismiss it up front rather than teaching
 * every measurement to re-measure.
 */
export async function suppressUpdateBanner(page) {
  await page.addInitScript(() => {
    try {
      window.localStorage.setItem('pf-update-dismissed-version', '2147483647.0.0')
    } catch {
      // localStorage unavailable; the banner will simply appear, as it does for a user.
    }
  })
}
