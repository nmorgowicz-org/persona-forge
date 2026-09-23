// SCENARIO INTENT: Show the empty Qwen VoiceDesign panel. OmniVoice is the default
// voice-design engine, so this scenario selects Qwen explicitly — the default panel is
// covered by the hero-voice-design scenario.
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-voice-design"]');
    await page.click('[data-testid="engine-qwen"]');
    await page.waitForSelector('[data-testid="voice-design-description"]');
    // INTENT: Empty voice design panel.
    await captureShot(page, 'voice-design-panel-panel-empty.png', { fullPage: true });
}
