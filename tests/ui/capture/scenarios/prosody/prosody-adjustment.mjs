// SCENARIO INTENT: Showcase the prosody adjustment feature — select Precise mode,
// choose the Calm preset, preview to generate an adjusted waveform with pause markers,
// and capture the A/B comparison of original vs. adjusted with pause positions visible.
import { captureShot } from '../../harness/shot.mjs';

const ALIGNMENT_WAIT_MS = 8000; // Forced alignment typically takes 3-6s; allow headroom

export default async function (ctx) {
    const { page, baseURL } = ctx;

    // Navigate to voice library
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-voice-library"]');
    await page.waitForSelector('[data-testid="voice-card"]', { timeout: 15000 });

    // INTENT: Show the voice library with voices that have alignment data.
    await captureShot(page, 'prosody-adjustment-voice-library.png', { scrollToSelector: '[data-testid="voice-card"]' });

    // Find a voice card that has alignment data (has an "Adjust prosody" button)
    let foundProsodyBtn = false;

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

        if (hasBtn) {
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

            foundProsodyBtn = true;
            break;
        }
    }

    if (!foundProsodyBtn) {
        throw new Error('Could not find a voice card with Adjust prosody button');
    }

    // INTENT: Show the voice card with prosody settings panel open.
    await captureShot(page, 'prosody-adjustment-settings-open.png', { scrollToSelector: '[data-testid="voice-card"]' });

    // Select "Precise" processing mode (forces forced-alignment-directed pauses)
    await new Promise(resolve => setTimeout(resolve, 1000));

    let preciseClicked = await page.evaluate(() => {
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

    // Precise mode triggers forced alignment which identifies word boundaries.
    // This typically takes 3-6 seconds; allow headroom for slower machines.
    await new Promise(resolve => setTimeout(resolve, ALIGNMENT_WAIT_MS));

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
    await captureShot(page, 'prosody-adjustment-preset-selected.png', { scrollToSelector: '[data-testid="voice-card"]' });

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

    // Close the prosody settings panel to show the full A/B comparison
    await page.keyboard.press('Escape');
    await new Promise(resolve => setTimeout(resolve, 500));

    // INTENT: Show the hero result — Original vs Adjusted waveforms with
    // pause markers (cyan diamonds and teal shaded regions) and word labels
    // on the original lane showing where pauses were placed.
    await captureShot(page, 'prosody-adjustment-calm-adjusted.png', { scrollToSelector: '[data-testid="voice-card"]' });
}
