// SCENARIO INTENT: the signal layer under playback — a real take's meter and playhead moving,
// then the same take read as a live spectrogram. This is the GIF that shows what the meters are
// actually measuring, so it has to be captured *during* playback: a paused deck is a still
// image, and a GIF of a still image says nothing.
//
// Frames are taken on a cadence rather than per beat (unlike the audition GIF, whose beats are
// UI states). Playback repaints canvas pixels, not layout, so `snapSettled` returns promptly
// here — see its note in harness/shot.mjs.
import { createRecorder, framesToGif, cleanupFrames, holdFor, GIF_FPS } from '../../harness/shot.mjs';
import { sleep } from '../../harness/paths.mjs';

// Real inference, not the fake tier's stub. A 0.6B model on CPU needs room; do not shorten
// this without measuring on the machine that runs it.
const SPEAK_TIMEOUT_MS = 600000;

// ~1.8s of billed motion per pass at 120ms + snap cost, which reads as continuous movement
// without turning the GIF into a 20MB file.
const MOTION_FRAMES = 22;
const MOTION_INTERVAL_MS = 120;

export default async function (ctx) {
    const { page, baseURL } = ctx;
    const prefix = 'signal-layer';
    cleanupFrames();
    const recorder = createRecorder(prefix);

    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.waitForSelector('[data-testid="speak-text-input"]');
    await page.type(
        '[data-testid="speak-text-input"]',
        'These meters are not decoration: the level reads the envelope of the sound you are hearing, and the playhead is drawn from the same clock.'
    );
    await holdFor(recorder, page, 1500);

    await page.click('[data-testid="speak-generate-button"]');
    await page.waitForSelector('[data-testid="speak-result"]', { timeout: SPEAK_TIMEOUT_MS });
    // Let the take land on screen before measuring it.
    await holdFor(recorder, page, 2500);

    // Play, and keep the meter and playhead in frame while they move. Wait for the transport
    // itself: the result container renders before the deck inside it, so clicking straight
    // after the container appears is a race the first run duly lost.
    await page.waitForSelector('[aria-label="Play audio"]', { timeout: 60000 });
    await page.click('[aria-label="Play audio"]');
    for (let i = 0; i < MOTION_FRAMES; i++) {
        await recorder.snapSettled(page);
        await sleep(MOTION_INTERVAL_MS);
    }

    // Same performance, other view: the spectrogram reads frequency over the same clock, so the
    // switch belongs inside playback rather than after it.
    await page.click('[data-testid="view-spectrum"]');
    for (let i = 0; i < MOTION_FRAMES; i++) {
        await recorder.snapSettled(page);
        await sleep(MOTION_INTERVAL_MS);
    }
    await page.click('[aria-label="Pause audio"]').catch(() => {});
    await holdFor(recorder, page, 1500);

    framesToGif(page, prefix, 'signal-layer-gif-signal-layer.gif', GIF_FPS);
    cleanupFrames();
}
