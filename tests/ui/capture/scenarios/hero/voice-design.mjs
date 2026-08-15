// SCENARIO INTENT: Hero candidate — the Voice Design trait-chip grid.
import { gotoPage } from '../../harness/browser.mjs';
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await gotoPage(page, baseURL, 'nav-voice-design', '[data-testid="voice-design-description"]');
    // INTENT: Voice Design's trait-chip grid as a first-time visitor sees it.
    await captureShot(page, 'hero-voice-design-panel.png', { fullPage: true });
}
