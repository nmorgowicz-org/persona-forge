/**
 * A bounding box that has stopped moving.
 *
 * Several panels in this app animate open (motion's height animation). `boundingBox()` returns
 * a real box while that is still running, so a pointer gesture started from those coordinates
 * lands somewhere else -- in one investigation, on the page background, which is how a drag
 * silently did nothing. Waiting for two identical measurements in a row is cheap and makes the
 * gesture start where the test thinks it does.
 */
export async function settledBox(locator, { attempts = 40, intervalMs = 50 } = {}) {
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
