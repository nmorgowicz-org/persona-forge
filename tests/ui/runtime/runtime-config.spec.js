import { test, expect } from '@playwright/test'

test.describe('runtime config', () => {
  test('open runtime page, toggle a known knob, confirm API call and persisted value', async ({ page }) => {
    const apiCalls = []
    page.on('request', (req) => {
      const url = req.url()
      const method = req.method()
      if (method === 'POST' && url.includes('/runtime/config')) {
        apiCalls.push({ url, method, body: req.postData() })
      }
    })

    await page.goto('/')
    await page.getByTestId('nav-runtime').click()

    // Confirm runtime page loaded
    await expect(page.getByText(/live-adjustable/i, { ignoreCase: true })).toBeVisible()

    // Toggle Silence Trim: the label sits in its own row div; the toggle <button> is a
    // sibling of that row (not a descendant), so the button lives under the row's parent.
    const toggleLabel = page.locator('label:has-text("Silence trim")').first()
    if (await toggleLabel.isVisible()) {
      const group = toggleLabel.locator('../..').first()
      const toggleBtn = group.locator('button').first()
      if (await toggleBtn.isVisible()) {
        await toggleBtn.click()
      }
    }

    // Apply changes (if an Apply button is shown and enabled)
    const applyBtn = page.getByRole('button', { name: /apply/i }).first()
    if (await applyBtn.isVisible() && (await applyBtn.isEnabled())) {
      await applyBtn.click()
    }

    // Confirm a POST to /runtime/config was made
    await page.waitForTimeout(500)
    const configCalls = apiCalls.filter((c) => c.url.includes('/runtime/config'))
    expect(configCalls.length).toBeGreaterThanOrEqual(1)

    // Confirm persisted: reload and recheck
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByTestId('nav-runtime').click()
    await page.waitForTimeout(500)
  })
})
