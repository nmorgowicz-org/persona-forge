// SCENARIO INTENT: Generate a new voice then show it appear in the library list.
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-voice-design"]');
    await page.waitForSelector('[data-testid="voice-design-description"]');
    await page.type('[data-testid="voice-design-description"]', 'Bright, energetic assistant voice.');
    await page.type('[data-testid="voice-design-sample-text"]', 'This is a short sample line.');
    await page.click('[data-testid="voice-design-generate-button"]');
    await page.waitForSelector('[data-testid="voice-design-result"]');

    await page.click('[data-testid="nav-voice-library"]');
    await page.waitForSelector('[data-testid="voice-card"]');
    // INTENT: Voice library list including the newly generated voice.
    await captureShot(page, 'voices-list-list.png', { fullPage: true });
}
