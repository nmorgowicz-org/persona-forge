// SCENARIO INTENT: Animate an OmniVoice audition run as a GIF: pick the engine and an
// accent, compose the script, audition, watch candidates land, stitch, and end on the
// stitched result. Every beat gets an explicit dwell (holdFor, in milliseconds) so the
// viewer can read it — a beat that is not held is on screen for exactly one GIF frame.
import { createRecorder, framesToGif, cleanupFrames, holdFor, GIF_FPS } from '../../harness/shot.mjs';
import { sleep } from '../../harness/paths.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    const prefix = 'omnivoice-audition';
    cleanupFrames();
    const recorder = createRecorder(prefix);

    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-voice-design"]');
    await page.click('[data-testid="engine-omnivoice"]');
    await page.waitForSelector('[data-testid="accent-bank-au"]');
    await page.click('[data-testid="accent-bank-au"]');
    await page.waitForSelector('[data-testid="omnivoice-script"]');
    await page.type('[data-testid="omnivoice-script"]', 'The quick brown fox jumps over the lazy dog.');
    // Dwell on the composed request (accent + script) before anything runs.
    await holdFor(recorder, page, 2500);

    await page.click('[data-testid="omnivoice-audition-button"]');
    // First frame after the click catches the generating state while it is live.
    await recorder.snap(page);

    // One frame per arriving candidate, not one per poll: the previous version snapped on
    // every 1s tick, so a slow audition produced a hundred identical frames and the GIF
    // spent its whole runtime on a frozen screen. $$eval (not $eval) is required here —
    // $eval hands the callback the single matched element, whose `.length` is undefined, so
    // the count never advanced and the loop always burned its full deadline.
    const candidateDeadline = Date.now() + 180000;
    let seen = 0;
    while (Date.now() < candidateDeadline) {
        const count = await page
            .$$eval('[data-testid="omnivoice-candidate-take"]', (els) => els.length)
            .catch(() => 0);
        if (count !== seen) {
            seen = count;
            await recorder.snap(page);
            // Each take gets its own beat, so the grid visibly fills up take by take.
            await holdFor(recorder, page, 1500);
        }
        if (count >= 3) break;
        await sleep(250);
    }
    // Let the completed candidate grid sit so the takes can actually be compared.
    await holdFor(recorder, page, 5000);

    await page.click('[data-testid="omnivoice-stitch-button"]');
    // Real CPU inference — do not shorten this timeout.
    const resultHandle = await page.waitForSelector('[data-testid="omnivoice-result"]', { timeout: 120000 });
    await page.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'instant' }), resultHandle);
    await page.waitForFunction(
        (el) => {
            const r = el.getBoundingClientRect();
            return r.top >= 0 && r.top < window.innerHeight;
        },
        { timeout: 5000 },
        resultHandle
    );
    // End on the payoff, held long enough to read.
    await holdFor(recorder, page, 6000);

    framesToGif(page, prefix, 'omnivoice-audition-gif-audition.gif', GIF_FPS);
    cleanupFrames();
}
