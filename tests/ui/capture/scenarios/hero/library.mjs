// SCENARIO INTENT: Hero candidate — the Voice Library with prosody fingerprints.
import { gotoPage } from '../../harness/browser.mjs';
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await gotoPage(page, baseURL, 'nav-voice-library', '[data-testid="voice-card"]');
    // INTENT: Voice Library with prosody fingerprints, as a first-time visitor sees it.
    await captureShot(page, 'hero-library-panel.png', { fullPage: true });
}
