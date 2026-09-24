// Long-task collection for the performance budget (B-P2).
//
// The budget is stated as "zero longtask entries > 50 ms during playback on the
// segment-browser-scale and stitch-assembly scenarios". `PerformanceObserver` only emits
// `longtask` for tasks that already exceed 50 ms, so collecting entries and filtering on
// duration is the whole implementation -- but it has to be installed *before* the interaction
// starts, because the entries are not buffered retroactively.

/**
 * Run `fn` while collecting long tasks. Returns the durations (ms) that exceeded `threshold`.
 * Entries observed during the run are returned in order.
 */
export async function collectLongTasks(page, fn, { threshold = 50 } = {}) {
  await page.evaluate(() => {
    window.__longTasks = []
    if (window.__longTaskObserver) window.__longTaskObserver.disconnect()
    try {
      window.__longTaskObserver = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) window.__longTasks.push(entry.duration)
      })
      window.__longTaskObserver.observe({ entryTypes: ['longtask'] })
    } catch {
      // Browsers without the longtask entry type: leave the array empty and let the caller
      // report "not supported" rather than a false pass.
      window.__longTaskObserver = null
    }
  })

  try {
    await fn()
  } finally {
    // Give the observer a tick to drain before reading.
    await page.waitForTimeout(150)
  }

  const result = await page.evaluate(() => ({
    supported: window.__longTaskObserver != null,
    durations: window.__longTasks ?? [],
  }))
  return { supported: result.supported, over: result.durations.filter((d) => d > threshold), all: result.durations }
}
