// SCENARIO INTENT: Hero candidate — the Voice Design trait-chip grid as a first-time
// visitor sees it. OmniVoice is the default voice-design engine on every backend, so the
// scenario asserts that default rather than forcing a click: if the default ever regresses
// to Qwen VoiceDesign, the capture must fail loudly instead of silently shooting the other
// panel.
import { gotoPage } from '../../harness/browser.mjs';
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await gotoPage(page, baseURL, 'nav-voice-design', '[data-testid="omnivoice-instruct"]');
    // INTENT: Voice Design's trait-chip grid as a first-time visitor sees it.
    await captureShot(page, 'hero-voice-design-panel.png', { fullPage: true });
}
