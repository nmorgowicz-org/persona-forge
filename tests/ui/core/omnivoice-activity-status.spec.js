import { test, expect } from '@playwright/test'

import {
  getActivityCountdown,
  tickActivityCountdown,
} from '../../../frontend/src/lib/activityCountdown.ts'

test('an active job replacement resets the countdown even when the ETA is unchanged', () => {
  const previous = { activityId: 'job-1', etaSeconds: 10, value: 6 }
  const replacement = { active: true, activityId: 'job-2', etaSeconds: 10 }

  expect(getActivityCountdown(previous, replacement)).toBe(10)
  expect(tickActivityCountdown(previous, replacement)).toEqual({
    activityId: 'job-2',
    etaSeconds: 10,
    value: 9,
  })
})

test('a new activity restarts its countdown even when its ETA matches the previous activity', async ({ page }) => {
  let nextJob = 0
  const completedJobs = new Set()

  await page.route('**/omnivoice/audition', async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    nextJob += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ job_id: `countdown-${nextJob}`, total_segments: 1 }),
    })
  })
  await page.route('**/omnivoice/audition/progress**', async (route) => {
    const jobId = new URL(route.request().url()).searchParams.get('job_id')
    const complete = completedJobs.has(jobId)
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: complete ? 'completed' : 'running',
        job_id: jobId,
        total_segments: 1,
        current_segment_index: complete ? null : 0,
        segments_completed: [],
        message: complete ? 'All segments generated.' : '',
        eta: complete ? null : 10,
      }),
    })
  })

  await page.goto('/')
  await page.getByTestId('nav-voice-design').click()
  await page.getByTestId('engine-omnivoice').click()
  await page.getByTestId('accent-bank-au').click()
  await page.getByTestId('omnivoice-script').fill('A clear sentence for countdown testing.')

  const statusTitle = page.getByText('Generating speech', { exact: true })
  const eta = page.getByText('~10s', { exact: true })
  const startAudition = () => page.getByTestId('omnivoice-audition-button').click()

  await startAudition()
  const statusRow = statusTitle.locator('xpath=..')
  await expect(statusTitle).toBeVisible()
  await expect(eta).toBeVisible()
  await expect
    .poll(() => statusRow.textContent())
    .not.toContain('~10s')

  completedJobs.add('countdown-1')
  await expect(statusTitle).toHaveCount(0)

  await startAudition()
  await expect(statusTitle).toBeVisible()
  await expect(eta).toBeVisible()
})
