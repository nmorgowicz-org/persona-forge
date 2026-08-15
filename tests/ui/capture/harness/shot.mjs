// Screenshot/GIF capture primitives.
// Ported from local-llm-foundry's tests/ui/capture/harness/shot.mjs (captureShot,
// captureElementScreenshot) merged with persona-forge's tests/ui/lib/gif.mjs
// (createRecorder/framesToGif/cleanupFrames), per
// docs/plans/20260815-screenshot_and_docs_edit.md Step 1.9.
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

export async function captureShot(page, rawFilename, options = {}) {
    const filename = tagFilename(rawFilename, options.runtimeTag);
    const { fullPage = true, expandSelector, runtimeTag, ...screenshotOptions } = options;

    // Non-full-page captures are disabled by default.
    if (!fullPage) {
        console.log(`[CAPTURE] Skipped non-full-page: ${filename}`);
        return;
    }

    // A prior elementHandle.click()/hover() leaves Puppeteer's virtual mouse
    // parked on that element; if it has a `title`, headless Chrome renders
    // the native tooltip into the page's own render surface and it shows up
    // in the screenshot. Park the mouse off any content before every shot.
    await page.mouse.move(0, 0).catch(() => {});

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
