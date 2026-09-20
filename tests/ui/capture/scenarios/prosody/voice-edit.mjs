// SCENARIO INTENT: Show the dedicated Voice Edit workspace with a saved voice selected.
import { captureShot } from '../../harness/shot.mjs';

export default async function ({ page, baseURL }) {
  await page.goto(baseURL, { waitUntil: 'networkidle0' });
  await page.click('[data-testid="nav-voice-edit"]');
  await page.waitForSelector('[data-testid="voice-edit-page"]');
  await page.waitForSelector('[data-testid="voice-edit-picker"]');
  await captureShot(page, 'voice-edit-workspace.png', { fullPage: true });
}
