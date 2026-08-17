// SCENARIO INTENT: Hero candidate — the Voice Library with prosody fingerprints.
import { gotoPage } from '../../harness/browser.mjs';
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await gotoPage(page, baseURL, 'nav-voice-library', '[data-testid="voice-card"]');
    await page.waitForSelector('[data-testid="alignment-compare"]');
    // INTENT: Voice Library's prosody fingerprint, as a first-time visitor sees it —
    // a single viewport-sized frame scrolled to the block, never the whole page
    // stitched into one tall image.
    await captureShot(page, 'hero-library-panel.png', {
        fullPage: false,
        scrollToSelector: '[data-testid="alignment-compare"]',
    });
}
