// Screenshot/GIF capture primitives.
// Ported from local-llm-foundry's tests/ui/capture/harness/shot.mjs (captureShot,
// captureElementScreenshot) merged with persona-forge's tests/ui/lib/gif.mjs
// (createRecorder/framesToGif/cleanupFrames), per
// docs/plans/archive/screenshots/20260815-screenshot_and_docs_edit.md Step 1.9.
//
// Dropped from the local-llm-foundry source: captureSparklineClips,
// startLiveGeneration, waitForRapidTelemetry, deleteRapidLiveTestPreset,
// describePopover, describeQuickGuideFlow, enableGuidedGeneration,
// cleanupScreenshotTabs — all local-llm-foundry chat/telemetry DOM concepts
// with no persona-forge analogue.
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
import { mkdirSync, rmSync } from 'node:fs';
import { currentArtifactsDir, tagFilename, sleep, __dirname as HARNESS_DIR } from './paths.mjs';
import { recordCapture, recordArtifact } from './receipt.mjs';

const FRAME_DIR = join(HARNESS_DIR, '..', 'frames');

// GIF pacing contract. framesToGif encodes at GIF_FPS, so ONE captured frame is
// displayed for GIF_FRAME_MS of wall-clock time in the finished GIF. Scenarios state
// dwell in milliseconds via holdFor() instead of repeating frames by hand, so "let this
// beat sit for 3s" is expressed once and stays true if the frame rate changes.
export const GIF_FPS = 1;
export const GIF_FRAME_MS = 1000 / GIF_FPS;
export function gifFrameCount(ms) {
    return Math.max(1, Math.round(ms / GIF_FRAME_MS));
}
export async function holdFor(recorder, page, ms) {
    const frames = gifFrameCount(ms);
    for (let i = 0; i < frames; i += 1) {
        await recorder.snap(page);
    }
}

// Coarse fingerprint of every laid-out element's box. Two equal fingerprints mean the
// page is not moving -- the condition a still screenshot actually needs.
async function layoutSignature(page) {
    return page.evaluate(() => {
        let h = 0;
        for (const el of document.querySelectorAll('body *')) {
            const r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) continue;
            h = (h * 31 + ((r.x | 0) * 7 + (r.y | 0) * 13 + (r.width | 0) * 17 + (r.height | 0) * 19)) | 0;
        }
        return h;
    });
}

// Gate every shot on the two async states that were silently landing mid-flight:
//   1. the sidebar version poll (a shot taken earlier renders the literal "vLoading..."
//      placeholder in the sidebar chrome), and
//   2. in-flight layout animation -- the engine selector's shared-layout highlight is a
//      Framer Motion spring, so clicking an engine and shooting immediately caught the
//      ring halfway between the two cards.
// Bounded and non-throwing by design: a page with a permanently animating element (a
// spinner, a running playhead) must not hang a capture, it just waits out the budget.
export async function waitForUiSettled(page, { timeout = 2000, stableFrames = 3, intervalMs = 40 } = {}) {
    const versionDeadline = Date.now() + timeout;
    while (Date.now() < versionDeadline) {
        const settled = await page
            .evaluate(() => {
                const el = document.querySelector('[data-testid="sidebar-version"]');
                if (!el) return true;
                const text = (el.textContent || '').trim();
                return text.length > 0 && !text.includes('Loading') && !text.includes('Error');
            })
            .catch(() => true);
        if (settled) break;
        await sleep(intervalMs);
    }

    const deadline = Date.now() + timeout;
    let last = null;
    let same = 0;
    while (Date.now() < deadline) {
        const signature = await layoutSignature(page).catch(() => null);
        if (signature !== null && signature === last) {
            same += 1;
            if (same >= stableFrames - 1) return;
        } else {
            same = 0;
        }
        last = signature;
        await sleep(intervalMs);
    }
}

export async function captureShot(page, rawFilename, options = {}) {
    const filename = tagFilename(rawFilename, options.runtimeTag);
    const { fullPage = true, expandSelector, scrollToSelector, runtimeTag, ...screenshotOptions } = options;

    // Non-full-page captures are disabled by default, UNLESS scrollToSelector
    // is given (see below) — that's the sanctioned way to opt out of
    // fullPage, because it still produces a single normal-viewport frame
    // rather than an arbitrary partial capture.
    if (!fullPage && !scrollToSelector) {
        console.log(`[CAPTURE] Skipped non-full-page: ${filename}`);
        return;
    }

    // A prior elementHandle.click()/hover() leaves Puppeteer's virtual mouse
    // parked on that element; if it has a `title`, headless Chrome renders
    // the native tooltip into the page's own render surface and it shows up
    // in the screenshot. Park the mouse off any content before every shot.
    await page.mouse.move(0, 0).catch(() => {});

    // Never shoot mid-animation or before the sidebar version has resolved.
    await waitForUiSettled(page);

    // fullPage screenshots stack the ENTIRE scrollable page into one tall
    // image — never what we want for a hero/showcase shot. When a scenario
    // wants to show a section that's below the fold, scroll the main
    // document so that section is centered in the viewport, then capture a
    // single normal-viewport-sized frame — same as what a visitor actually
    // sees, just scrolled to the interesting part.
    if (scrollToSelector) {
        await page.evaluate((sel) => {
            document.querySelector(sel)?.scrollIntoView({ behavior: 'instant', block: 'center' });
        }, scrollToSelector);
        await sleep(300);
        await page.screenshot({ path: join(currentArtifactsDir(), filename), fullPage: false, ...screenshotOptions });
        recordCapture(filename, page.viewport());
        console.log(`[CAPTURE] Saved ${filename}`);
        return;
    }

    // Some panels (modals, scrollable sub-containers) are position:fixed or
    // internally scrolling, so fullPage:true (which sizes off
    // document/body scrollHeight) never captures them correctly. Rather than
    // flatten/expand the container to fit everything in one giant image,
    // scroll it back to its natural resting position and capture at normal
    // viewport size, same as what a user actually sees.
    if (expandSelector) {
        await page.evaluate((sel) => {
            const el = document.querySelector(sel);
            if (el) {
                el.scrollTop = 0;
                el.scrollLeft = 0;
            }
        }, expandSelector);
        await sleep(200);
        await page.screenshot({ path: join(currentArtifactsDir(), filename), fullPage: false, ...screenshotOptions });
        recordCapture(filename, page.viewport());
        console.log(`[CAPTURE] Saved ${filename}`);
        return;
    }

    await page.screenshot({ path: join(currentArtifactsDir(), filename), fullPage: true, ...screenshotOptions });
    recordCapture(filename, page.viewport());
    console.log(`[CAPTURE] Saved ${filename}`);
}

export async function captureElementScreenshot(page, selector, rawFilename, options = {}) {
    const filename = tagFilename(rawFilename, options.runtimeTag);

    const padding = options.padding ?? 20;
    const handle = await page.$(selector);
    if (!handle) {
        throw new Error(`Missing selector for screenshot capture: ${selector}`);
    }

    await handle.evaluate(el => {
        el.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'nearest' });
    });
    await sleep(options.settleMs ?? 500);

    const box = await handle.boundingBox();
    if (!box) {
        throw new Error(`Selector has no visible bounds: ${selector}`);
    }

    const viewport = page.viewport();
    const clip = {
        x: Math.max(0, box.x - padding),
        y: Math.max(0, box.y - padding),
        width: Math.min((viewport?.width ?? box.width) - Math.max(0, box.x - padding), box.width + padding * 2),
        height: Math.min((viewport?.height ?? box.height) - Math.max(0, box.y - padding), box.height + padding * 2),
    };

    await page.mouse.move(0, 0).catch(() => {});
    await page.screenshot({ path: join(currentArtifactsDir(), filename), clip });
    recordCapture(filename, page.viewport());
    console.log(`[CAPTURE] Saved ${filename}`);
}

// GIF path — merged in from tests/ui/lib/gif.mjs. A fixed-cadence background
// capture loop running concurrently with click/type/navigate actions was
// tried and abandoned: under real model-inference CPU load, page.screenshot()
// can be starved on the renderer's main thread for the ENTIRE duration of a
// scenario, not just during navigation — so no timeout/retry scheme salvages
// a background loop. A recorder that only snaps when the caller explicitly
// asks (between driving steps, never concurrently with one) sidesteps the
// contention entirely: each snap() happens while the page is otherwise idle.
export function createRecorder(prefix) {
    mkdirSync(FRAME_DIR, { recursive: true });
    let i = 0;
    return {
        async snap(page) {
            const path = join(FRAME_DIR, `${prefix}_${String(i).padStart(3, '0')}.png`);
            await waitForUiSettled(page);
            await page.screenshot({ path });
            i += 1;
        },
        count() {
            return i;
        },
    };
}

export function framesToGif(page, prefix, rawFilename, fps, options = {}) {
    const filename = tagFilename(rawFilename, options.runtimeTag);
    const output = join(currentArtifactsDir(), filename);
    execFileSync(
        'ffmpeg',
        [
            '-y',
            '-framerate', String(fps),
            '-i', join(FRAME_DIR, `${prefix}_%03d.png`),
            '-vf',
            'scale=900:-1:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5',
            output,
        ],
        { stdio: 'inherit' }
    );
    recordArtifact(filename, page.viewport());
    console.log(`[CAPTURE] Saved ${filename}`);
    return output;
}

export function cleanupFrames() {
    rmSync(FRAME_DIR, { recursive: true, force: true });
}
