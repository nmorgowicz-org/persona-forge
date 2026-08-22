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

    // Find a voice card that has alignment data (has an "Adjust prosody" button)
    let foundProsodyBtn = false;

    const voiceCards = await page.$$('div[data-testid="voice-card"]');
    console.log(`Found ${voiceCards.length} voice cards`);

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
            console.log(`Found Adjust prosody button on voice card ${i}`);

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
    // Wait for the panel to be fully open and rendered
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    let preciseClicked = await page.evaluate(() => {
        // Try finding buttons with text 'Precise' (case-insensitive)
        const allElements = document.querySelectorAll('*');
        let found = null;
        for (const el of allElements) {
            if (el.tagName === 'BUTTON' && el.textContent.trim().toLowerCase() === 'precise') {
                found = el;
                break;
            }
        }
        
        if (found) {
            found.click();
            return { clicked: true, text: found.textContent.trim() };
        }
        
        // List all button texts for debugging
        const buttons = document.querySelectorAll('button');
        const texts = Array.from(buttons).map(b => b.textContent.trim()).slice(0, 30);
        return { clicked: false, text: null, debug: texts };
    });
    console.log('Precise clicked:', preciseClicked.clicked, preciseClicked.text);
    if (preciseClicked.debug) {
        console.log('Button texts:', preciseClicked.debug);
    }

    // Precise mode triggers forced alignment which takes a few seconds to identify
    // word boundaries. Wait for it to complete.
    console.log('Waiting for forced alignment to complete...');
    await new Promise(resolve => setTimeout(resolve, 5000));

    // Select "Calm" style preset from the dropdown
    // The Select component uses a custom trigger button, not a native select
    let calmSelected = await page.evaluate(() => {
        // Find the Style Preset section and click its trigger
        const labels = document.querySelectorAll('label');
        let selectTrigger = null;
        for (const label of labels) {
            if (label.textContent.includes('Style Preset')) {
                // The trigger is the next sibling or nearby button
                const parent = label.parentElement;
                const buttons = parent.querySelectorAll('button');
                for (const btn of buttons) {
                    selectTrigger = btn;
                    break;
                }
                break;
            }
        }
        
        if (!selectTrigger) {
            console.log('Style Preset trigger not found');
            return false;
        }
        
        console.log('Found Style Preset trigger, clicking');
        selectTrigger.click();
        return true;
    });
    console.log('Select opened:', calmSelected);
    await new Promise(resolve => setTimeout(resolve, 500));

    // Click the Calm option in the dropdown
    calmSelected = await page.evaluate(() => {
        // Look for Calm in dropdown items
        const items = document.querySelectorAll('[role="option"]');
        for (const item of items) {
            if (item.textContent.includes('Calm')) {
                console.log('Found Calm option, clicking');
                item.click();
                return true;
            }
        }
        
        // Fallback: try all buttons
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
            if (btn.textContent.includes('Calm') && !btn.textContent.includes('Processing') && !btn.textContent.includes('Adjust')) {
                console.log('Found Calm button, clicking');
                btn.click();
                return true;
            }
        }
        
        console.log('Calm not found');
        return false;
    });
    console.log('Calm selected:', calmSelected);

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
        return false;
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

    // Wait a moment for the waveform to fully render
    await new Promise(resolve => setTimeout(resolve, 1000));

    // Close the prosody settings panel to show the full A/B comparison
    await page.keyboard.press('Escape');
    await new Promise(resolve => setTimeout(resolve, 500));

    // INTENT: Show the hero result — Original vs Adjusted waveforms with
    // pause markers (cyan diamonds and teal shaded regions) and word labels
    // on the original lane showing where pauses were placed.
    await captureShot(page, 'prosody-adjustment-calm-adjusted.png', { scrollToSelector: '[data-testid="voice-card"]' });
}
