// SCENARIO INTENT: Showcase the prosody adjustment feature — select Precise mode,
// choose the Calm preset, preview to generate an adjusted waveform with pause markers,
// and capture the A/B comparison of original vs. adjusted with pause positions visible.
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;

    // Navigate to voice library
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-voice-library"]');
    await page.waitForSelector('[data-testid="voice-card"]', { timeout: 15000 });

    // INTENT: Show the voice library with voices that have alignment data.
    await captureShot(page, 'prosody-adjustment-voice-library.png', { scrollToSelector: '[data-testid="voice-card"]' });

    // Find a voice card whose prosody panel can actually run forced alignment.
    //
    // "Has an Adjust prosody button" is not sufficient, and assuming it was is what broke this
    // scenario: Precise mode is *disabled* for a voice with no transcript (the panel says so
    // itself — "Precise (forced alignment) needs reference text"), and clicking a disabled
    // button is a silent no-op, so the run waited 30s for an alignment job that was never
    // started and failed with an unhelpful "never reached a terminal UI state". The card is now
    // only accepted if its Precise button is enabled; otherwise the panel is closed and the next
    // card is tried.
    let foundProsodyBtn = false;
    // The card the scenario actually aligns. Every later capture is scoped to it: a bare
    // `[data-testid="voice-card"]` matches the *first* card in the grid, which is why the
    // "calm-adjusted" shot used to show a different voice's strip (and an empty one, since that
    // voice has no preview).
    let chosenVoiceId = null;

    const voiceCards = await page.$$('div[data-testid="voice-card"]');

    for (let i = 0; i < voiceCards.length; i++) {
        const hasBtn = await page.evaluate((card) => {
            const buttons = card.querySelectorAll('button');
            for (const btn of buttons) {
                if (btn.textContent.includes('Adjust prosody')) {
                    return true;
                }
            }
            return false;
        }, voiceCards[i]);

        if (!hasBtn) continue;

        // Click the button to open the prosody settings panel
        await page.evaluate((card) => {
            const buttons = card.querySelectorAll('button');
            for (const btn of buttons) {
                if (btn.textContent.includes('Adjust prosody')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }, voiceCards[i]);

        // Wait for the prosody settings panel to appear
        await page.waitForFunction(() => {
            return document.body.innerText.includes('Prosody Settings');
        }, { timeout: 10000 });

        const preciseEnabled = await page.evaluate(() => {
            for (const el of document.querySelectorAll('button')) {
                if (el.textContent.trim().toLowerCase() === 'precise') return !el.disabled;
            }
            return false;
        });

        if (preciseEnabled) {
            chosenVoiceId = await page.evaluate((card) => card.getAttribute('data-voice-id'), voiceCards[i]);
            foundProsodyBtn = true;
            break;
        }

        // No transcript on this voice, so Precise is disabled. Close the panel and try the next.
        await page.keyboard.press('Escape');
        await new Promise((resolve) => setTimeout(resolve, 400));
    }

    if (!foundProsodyBtn) {
        throw new Error(
            'No voice card offers an enabled Precise mode (forced alignment needs a transcript — ' +
                'every card in this library either lacks the prosody panel or has no reference text)',
        );
    }

    // INTENT: Show the voice card with prosody settings panel open.
    await captureShot(page, 'prosody-adjustment-settings-open.png', { scrollToSelector: `[data-voice-id="${chosenVoiceId}"]` });

    // Select "Precise" processing mode (forces forced-alignment-directed pauses)
    await new Promise(resolve => setTimeout(resolve, 1000));

    const preciseClicked = await page.evaluate(() => {
        const allElements = document.querySelectorAll('*');
        for (const el of allElements) {
            if (el.tagName === 'BUTTON' && el.textContent.trim().toLowerCase() === 'precise') {
                el.click();
                return true;
            }
        }
        return false;
    });

    if (!preciseClicked) {
        throw new Error('Could not find Precise processing mode button');
    }

    // Precise mode triggers forced alignment. The UI renders one of four
    // states while the panel is open: a busy message while the job runs,
    // an "Aligned …" badge on success, a latency-budget warning on slow
    // alignment, or an "Alignment unavailable" error. Synchronize on these
    // terminal states rather than a fixed sleep, and fail closed if the UI
    // does not reach one — proceeding on a still-queued job would start a
    // second alignment-backed request and capture before the aligned state.
    const ALIGN_BUSY = 'Finding linguistic boundaries';
    const ALIGN_ERROR = 'Alignment unavailable';
    const ALIGN_DONE = ['Aligned', 'Alignment exceeded latency budget'];

    let state = 'pending';
    try {
        const handle = await page.waitForFunction((busy, doneTexts) => {
            const text = document.body.innerText;
            if (text.includes(busy)) return 'busy';
            for (const d of doneTexts) if (text.includes(d)) return 'done';
            return null;
        }, { timeout: 30000, polling: 100 }, ALIGN_BUSY, ALIGN_DONE);
        state = await handle.jsonValue();
    } catch {
        state = 'pending';
    }

    if (state === 'busy') {
        // Wait for the busy indicator to clear; a timeout here means the job
        // never finished, so let it throw rather than capture a stale state.
        await page.waitForFunction((busy) => !document.body.innerText.includes(busy), { timeout: 90000 }, ALIGN_BUSY);
    }

    const terminal = await page.evaluate((errorText, doneTexts) => {
        const text = document.body.innerText;
        if (text.includes(errorText)) return 'error';
        for (const d of doneTexts) if (text.includes(d)) return 'done';
        return 'unknown';
    }, ALIGN_ERROR, ALIGN_DONE);

    if (terminal === 'error') {
        throw new Error('Forced alignment failed in the UI (Alignment unavailable)');
    }
    if (terminal !== 'done') {
        throw new Error(`Forced alignment never reached a terminal UI state (initial: ${state})`);
    }

    // Settle beat after the UI flips to its aligned state.
    await new Promise(resolve => setTimeout(resolve, 500));

    // Select "Calm" style preset from the dropdown
    await page.evaluate(() => {
        const labels = document.querySelectorAll('label');
        for (const label of labels) {
            if (label.textContent.includes('Style Preset')) {
                const parent = label.parentElement;
                const buttons = parent.querySelectorAll('button');
                for (const btn of buttons) {
                    btn.click();
                    return true;
                }
            }
        }
    });
    await new Promise(resolve => setTimeout(resolve, 500));

    await page.evaluate(() => {
        const items = document.querySelectorAll('[role="option"]');
        for (const item of items) {
            if (item.textContent.includes('Calm')) {
                item.click();
                return true;
            }
        }
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
            if (btn.textContent.includes('Calm') && !btn.textContent.includes('Processing') && !btn.textContent.includes('Adjust')) {
                btn.click();
                return true;
            }
        }
    });
    await new Promise(resolve => setTimeout(resolve, 500));

    // INTENT: Show the prosody settings with mode and preset selected.
    await captureShot(page, 'prosody-adjustment-preset-selected.png', { scrollToSelector: `[data-voice-id="${chosenVoiceId}"]` });

    // Click Preview to generate the adjusted waveform with pause markers
    await page.evaluate(() => {
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
            if (btn.textContent.trim() === 'Preview' || btn.textContent.includes('Preview')) {
                btn.click();
                return true;
            }
        }
    });

    // Wait for the adjusted waveform to appear (preview button becomes "Reset Preview")
    await page.waitForFunction(() => {
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
            if (btn.textContent.includes('Reset Preview')) {
                return true;
            }
        }
        return false;
    }, { timeout: 30000 });

    // Wait for the waveform to fully render
    await new Promise(resolve => setTimeout(resolve, 1000));

    // Close the prosody popover so the card's own A/B strip is the subject — but wait for that
    // strip first: captureShot now fails when its scrollToSelector matches nothing, and the
    // strip renders its lanes only once the take's audio has resolved.
    await page.waitForSelector('[data-testid="alignment-compare"]', { timeout: 30000 });
    await page.keyboard.press('Escape');
    await new Promise(resolve => setTimeout(resolve, 500));
    await page.waitForFunction(() => {
        const el = document.querySelector('[data-testid="alignment-compare"]');
        return Boolean(el) && el.getBoundingClientRect().height > 60;
    }, { timeout: 15000 });

    // INTENT: Show the hero result — Original vs Adjusted waveforms with
    // pause markers (cyan diamonds and teal shaded regions) and word labels
    // on the original lane showing where pauses were placed. Centered on the
    // A/B strip itself, since the lanes + ruler + markers are the subject.
    await captureShot(page, 'prosody-adjustment-calm-adjusted.png', { scrollToSelector: `[data-voice-id="${chosenVoiceId}"] [data-testid="alignment-compare"]` });
}
