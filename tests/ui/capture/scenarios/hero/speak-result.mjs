// SCENARIO INTENT: Hero candidate — the Speak page after a real generation, waveform visible.
import { gotoApp } from '../../harness/browser.mjs';
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await gotoApp(page, baseURL);
    await page.waitForSelector('[data-testid="speak-text-input"]');
    await page.type(
        '[data-testid="speak-text-input"]',
        'The voice was warm and clear, carrying the kind of certainty that made you want to listen.'
    );
    await page.click('[data-testid="speak-generate-button"]');
    // Real CPU inference — do not shorten this timeout.
    await page.waitForSelector('[data-testid="speak-result"] audio', { timeout: 120000 });
    // INTENT: Generated audio result and waveform rendered — what a visitor sees after their first generation.
    await captureShot(page, 'hero-speak-result-speak.png', { fullPage: true });
}
