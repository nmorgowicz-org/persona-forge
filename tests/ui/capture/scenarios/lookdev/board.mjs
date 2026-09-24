// SCENARIO INTENT: B-P0 look-dev board (D1 look, D9 signal palette). Drives the real app to four
// hero states, then for every candidate look x accent injects candidate token CSS (no
// frontend/src edits) and shoots the viewport; composes per-look and accent-check contact sheets;
// renders a signal-palette board from a real decoded fixture voice.
// Plan: docs/archive/luminous-instrument/20260923-luminous_instrument_redesign.md "P0".
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { gotoPage } from '../../harness/browser.mjs';
import { captureShot } from '../../harness/shot.mjs';
import { currentArtifactsDir, sleep, tagFilename } from '../../harness/paths.mjs';
import {
    LOOKS,
    THEMES,
    accentSheetHtml,
    dataUri,
    lookCss,
    lookSheetHtml,
    lookSurface,
    renderSignalBoard,
    repoPath,
    showBoard,
    signalBoardHtml,
} from '../../lookdev/pages.mjs';

const SURFACES = [
    { id: 'speak', label: 'Speak · after generate', anchor: '[data-testid="speak-result"]' },
    { id: 'stitch', label: 'Stitch Studio · assembly', anchor: '[data-testid="stitch-clip"]' },
    { id: 'design', label: 'Voice Design · OmniVoice panel', anchor: '[data-testid="omnivoice-instruct"]' },
    { id: 'edit', label: 'Voice Edit · prosody A/B', anchor: '[data-testid="alignment-compare"]' },
];
const SIGNAL_FIXTURE = 'tests/ui/fixtures/capture-data/voices/vd_c66abd9c8eb0/original.wav';

const key = 'lookdev-board';
const tagged = (rest) => `${key}--neutral--${rest}`;
export const LOOKDEV_BOARD_OUTPUTS = [
    ...SURFACES.flatMap((s) => LOOKS.flatMap((l) => THEMES.map((t) => tagged(`${s.id}-${l.id}-${t}.png`)))),
    ...LOOKS.map((l) => tagged(`sheet-${l.id}.png`)),
    tagged('sheet-accent-speak.png'),
    tagged('signal-palettes.png'),
];

async function applyLook(page, lookId, theme) {
    await page.evaluate(
        (css, t) => {
            for (const el of document.querySelectorAll('style[data-lookdev]')) el.remove();
            const style = document.createElement('style');
            style.dataset.lookdev = 'true';
            style.textContent = css;
            document.head.appendChild(style);
            // Same attribute lib/theme.ts applyTheme() writes; set directly so SPA state survives.
            document.documentElement.dataset.theme = t;
        },
        lookCss(lookId),
        theme,
    );
    await sleep(200);
}

async function shootAllLooks(page, surface) {
    for (const look of LOOKS) {
        for (const theme of THEMES) {
            await applyLook(page, look.id, theme);
            // INTENT: One hero surface under one candidate look and accent, viewport-sized.
            await captureShot(page, `${key}-${surface.id}-${look.id}-${theme}.png`, {
                fullPage: false,
                scrollToSelector: surface.anchor,
            });
        }
    }
}

async function driveSpeak(page, baseURL) {
    await gotoPage(page, baseURL, 'nav-speak', '[data-testid="speak-text-input"]');
    await page.type('[data-testid="speak-text-input"]', 'The voice was warm and clear, carrying the kind of certainty that made you want to listen.');
    await page.click('[data-testid="speak-generate-button"]');
    await page.waitForFunction(
        () => {
            const el = document.querySelector('[data-testid="speak-result"] audio');
            return Boolean(el) && el.readyState >= 1 && Number.isFinite(el.duration) && el.duration > 0;
        },
        { timeout: 60000 },
    );
    // The deck autoplays; freeze it at 0 so every look is shot in the same unplayed state
    // (otherwise early looks catch bright "played" bars and later ones don't).
    await page.evaluate(() => {
        const audio = document.querySelector('[data-testid="speak-result"] audio');
        audio.autoplay = false;
        audio.pause();
        audio.currentTime = 0;
    });
    await sleep(300);
}

// Live preview renders asynchronously after insert; shoot only once it has settled so every
// look shows the same state.
async function waitPreviewSettled(page) {
    await page
        .waitForFunction(() => !/Generating preview|rendering/i.test(document.body.innerText), { timeout: 30000 })
        .catch(() => {});
    await sleep(300);
}

async function driveStitch(page) {
    await page.click('[data-testid="nav-stitch-studio"]');
    await page.waitForSelector('[data-testid="stitch-picker-toggle-segments"], [data-testid="empty-state-action"]');
    await page.click('[data-testid="stitch-picker-toggle-segments"], [data-testid="empty-state-action"]');
    await page.waitForSelector('[data-testid="stitch-picker-item-segments"]');
    await page.waitForFunction(
        () => getComputedStyle(document.querySelector('[data-testid="segment-browser-dialog"]')).opacity === '1',
        { timeout: 5000 },
    );
    const boxes = await page.$$('[data-testid="stitch-picker-item-segments"]');
    await boxes[0].click();
    if (boxes[1]) await boxes[1].click();
    await page.click('[data-testid="stitch-picker-insert-segments"]');
    await page.waitForSelector('[data-testid="stitch-clip"]');
    await page.waitForSelector('[data-testid="segment-browser-dialog"]', { hidden: true, timeout: 5000 }).catch(() => {});
    await waitPreviewSettled(page);
}

async function driveDesign(page) {
    await page.click('[data-testid="nav-voice-design"]');
    await page.waitForSelector('[data-testid="omnivoice-instruct"]', { timeout: 15000 });
}

async function driveEdit(page) {
    await page.click('[data-testid="nav-voice-edit"]');
    await page.waitForSelector('[data-testid="voice-edit-variant"]', { timeout: 15000 });
    await page.waitForSelector('[data-testid="stitch-waveform-canvas"]', { timeout: 15000 });
    await page.evaluate(() => {
        for (const btn of document.querySelectorAll('button')) {
            if ((btn.textContent || '').trim().startsWith('Preview')) {
                btn.click();
                return;
            }
        }
    });
    await page.waitForFunction(
        () => document.querySelectorAll('[data-testid="stitch-waveform-canvas"]').length >= 2,
        { timeout: 60000 },
    );
}

export default async function (ctx) {
    const { page, baseURL } = ctx;
    const drivers = { speak: () => driveSpeak(page, baseURL), stitch: () => driveStitch(page), design: () => driveDesign(page), edit: () => driveEdit(page) };
    for (const surface of SURFACES) {
        await drivers[surface.id]();
        await shootAllLooks(page, surface);
    }

    const shot = (rest) => dataUri(join(currentArtifactsDir(), tagFilename(`${key}-${rest}`)), 'image/png');
    for (const look of LOOKS) {
        await showBoard(page, lookSheetHtml(look, SURFACES.map((s) => ({ label: s.label, uri: shot(`${s.id}-${look.id}-violet.png`) }))));
        // INTENT: Per-look contact sheet — the four hero surfaces side by side, violet accent.
        await captureShot(page, `${key}-sheet-${look.id}.png`, { fullPage: false, scrollToSelector: '#board' });
    }

    const accentCells = LOOKS.flatMap((look) => THEMES.map((theme) => ({ look, theme, uri: shot(`speak-${look.id}-${theme}.png`) })));
    await showBoard(page, accentSheetHtml('Speak', accentCells));
    // INTENT: Accent check — every look under violet and amber on the same surface.
    await captureShot(page, `${key}-sheet-accent-speak.png`, { fullPage: false, scrollToSelector: '#board' });

    // D1 = Obsidian (CP0b, 2026-09-23): the signal board compares palettes on the chosen look.
    const obsidian = LOOKS.find((look) => look.id === 'obsidian');
    const palettes = [
        { id: 'a', label: 'S-a · current', note: 'cyan → magenta, amber playhead (waveformBarColor today)' },
        { id: 'b', label: 'S-b · brand', note: 'blue → violet → lavender, white playhead (Option E)' },
        { id: 'c', label: 'S-c · hybrid ✓', note: 'blue → violet → hot magenta → white, amber playhead (owner D9)' },
    ];
    await showBoard(page, signalBoardHtml({ ...obsidian, surface: lookSurface('obsidian') }, palettes, `Real decoded speech (fixture "Podcast Host", ${SIGNAL_FIXTURE.split('/').at(-2)}) · true-scale waveform (peak + RMS body), color by dBFS · STFT spectrogram 50 Hz–12 kHz · dBFS meter + peak-hold at the playhead`));
    const wavBase64 = readFileSync(repoPath(SIGNAL_FIXTURE)).toString('base64');
    const stats = await page.evaluate(renderSignalBoard, { wavBase64, playFrac: 0.42 });
    console.log(`[LOOKDEV] signal fixture: ${JSON.stringify(stats)}`);
    // INTENT: D9 — current, brand, and hybrid signal palettes on the chosen Obsidian surfaces.
    await captureShot(page, `${key}-signal-palettes.png`, { fullPage: false, scrollToSelector: '#board' });
}
