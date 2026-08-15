// SCENARIO INTENT: Show the voice library variant list.
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-voice-library"]');
    await page.waitForSelector('[data-testid="voice-card"]');
    await page.waitForSelector('[data-testid="alignment-compare"]');
    // INTENT: Voice library showing variant list.
    await captureShot(page, 'voice-variant-list-variant-list.png', { fullPage: true });
}
