// SCENARIO INTENT: Animate the end-to-end design-to-stitch wizard flow as a GIF.
import { createRecorder, framesToGif, cleanupFrames } from '../../harness/shot.mjs';

// Repeats the current frame so a viewer has time to actually read what's on
// screen at key beats, instead of the GIF blowing past them in one 0.5s tick.
async function hold(recorder, page, count) {
    for (let i = 0; i < count; i += 1) {
        await recorder.snap(page);
    }
}

export default async function (ctx) {
    const { page, baseURL } = ctx;
    const prefix = 'design-to-stitch';
    cleanupFrames();
    const recorder = createRecorder(prefix);

    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await recorder.snap(page);
    await page.click('[data-testid="nav-voice-design"]');
    await recorder.snap(page);
    await page.click('[data-testid="engine-omnivoice"]');
    await recorder.snap(page);
    await page.waitForSelector('[data-testid="accent-bank-au"]');
    await page.click('[data-testid="accent-bank-au"]');
    await recorder.snap(page);
    await page.waitForSelector('[data-testid="omnivoice-script"]');
    await page.type('[data-testid="omnivoice-script"]', 'The quick brown fox jumps over the lazy dog.');
    // Dwell here: let the viewer read the composed instruct + script before
    // the audition kicks off.
    await hold(recorder, page, 2);

    // Just 1 candidate — this is a real remote inference job on a shared box
    // (avg ~2min/candidate), and the GIF only needs one take to lock in, not
    // the full 3-candidate comparison a real user would want.
    // The "Advanced" toggle only exists in expert experience mode, and the
    // candidates-per-segment field is itself unmounted until "Advanced" is
    // expanded — flip both, set candidates to 1, then collapse again so the
    // GIF doesn't show an unrelated UI mode switch.
    await page.click('[data-testid="experience-level-toggle"]');
    await page.click('[data-testid="omnivoice-advanced-toggle"]');
    await page.waitForSelector('[data-testid="omnivoice-candidates-per-segment"]');
    await page.$eval('[data-testid="omnivoice-candidates-per-segment"]', (el) => {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, '1');
        el.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await page.click('[data-testid="omnivoice-advanced-toggle"]');
    await page.click('[data-testid="experience-level-toggle"]');
    await page.click('[data-testid="omnivoice-audition-button"]');
    await recorder.snap(page);

    const candidateDeadline = Date.now() + 180000;
    while (Date.now() < candidateDeadline) {
        const count = await page
            .$eval('[data-testid="omnivoice-candidate-take"]', (els) => els.length)
            .catch(() => 0);
        if (count >= 1) break;
        await new Promise((r) => setTimeout(r, 1500));
    }
    // Dwell here: this is the "segment rendered" moment the viewer needs to
    // actually register before the flow moves on.
    await hold(recorder, page, 6);

    const lockButton = await page.waitForSelector('[data-testid="omnivoice-lock-segment"]');
    await lockButton.click();
    await page.waitForFunction(
        (el) => el.disabled,
        { timeout: 15000 },
        lockButton
    );
    await recorder.snap(page);

    await page.click('[data-testid="nav-stitch-studio"]');
    await page.waitForSelector('[data-testid="stitch-voice-name"]');
    await recorder.snap(page);
    await page.type('[data-testid="stitch-voice-name"]', 'Wizard Demo Voice');
    await recorder.snap(page);

    await page.click('[data-testid="stitch-picker-toggle-segments"]');
    await page.waitForSelector('[data-testid="stitch-picker-item-segments"]');
    await page.waitForFunction(
        () => {
            const el = document.querySelector('[data-testid="stitch-picker-item-segments"]')?.closest('.shadow-lg');
            return el && getComputedStyle(el).opacity === '1';
        },
        { timeout: 5000 }
    );
    await recorder.snap(page);

    // Pick two segments so the viewer sees what a multi-clip timeline looks
    // like, not just a single lonely clip.
    const items = await page.$$('[data-testid="stitch-picker-item-segments"]');
    await items[0].click();
    if (items[1]) await items[1].click();
    await page.click('[data-testid="stitch-picker-insert-segments"]');
    await page.waitForSelector('[data-testid="stitch-clip"]');
    // Dwell here: the segment(s) have just landed in the Stitch Studio
    // timeline — give the viewer time to see the result before saving.
    await hold(recorder, page, 8);

    // The Save button is disabled while the debounced live-preview render is in
    // flight (isRendering in StitchTimeline). hold() only takes back-to-back
    // screenshots for GIF pacing — it doesn't wait real wall-clock time — so
    // without this, the click can land on a still-disabled button and silently
    // no-op (no request ever reaches /omnivoice/save).
    await page.waitForFunction(
        () => {
            const btn = document.querySelector('[data-testid="stitch-save-voice"]');
            return btn && !btn.disabled;
        },
        { timeout: 30000 }
    );
    await page.click('[data-testid="stitch-save-voice"]');
    await page.waitForSelector('[data-testid="voice-card"]', { timeout: 60000 });
    // Dwell here: end on the saved-voice confirmation so the viewer has time
    // to register the outcome instead of the GIF just stopping mid-beat.
    await hold(recorder, page, 3);

    framesToGif(page, prefix, 'design-to-stitch-gif-design-to-stitch.gif', 2);
    cleanupFrames();
}
