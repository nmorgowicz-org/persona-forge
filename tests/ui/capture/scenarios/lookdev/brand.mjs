// SCENARIO INTENT: B-P0 brand board (D7). Shows the three original mark drafts beside the
// current favicon (the stock Vite scaffold logo) at 150/64/32/16 px on dark and light, as the
// sidebar lockup and a browser tab, then shows the Option E hero art in its sanctioned places
// (README/social banner, startup state). Plan: luminous_instrument_redesign.md "P0".
import { captureShot } from '../../harness/shot.mjs';
import { brandContextHtml, brandMarksHtml, dataUri, repoPath, showBoard } from '../../lookdev/pages.mjs';

const key = 'lookdev-brand';
export const LOOKDEV_BRAND_OUTPUTS = [`${key}--neutral--marks.png`, `${key}--neutral--context.png`];

const DRAFTS = 'assets/brand/concepts/persona-forge/mark-drafts';

export default async function ({ page }) {
    const svg = (path) => dataUri(repoPath(path), 'image/svg+xml');
    // D7 = M-b (CP0b, 2026-09-23). The shipping set uses mark.svg at >= 48 px and
    // mark-small.svg at <= 32 px (sidebar tile glyph, favicon); the draft stays for reference.
    const FINAL = 'assets/brand/concepts/persona-forge/mark-final';
    const marks = [
        { name: 'Current — stock Vite favicon', uri: svg('frontend/public/favicon.svg'), flag: true },
        { name: 'Final · shipping set (mark + mark-small)', uri: svg(`${FINAL}/mark.svg`), smallUri: svg(`${FINAL}/mark-small.svg`) },
        { name: 'Final · mark-small.svg only', uri: svg(`${FINAL}/mark-small.svg`), splash: false },
        { name: 'M-b draft (reference)', uri: svg(`${DRAFTS}/m-b-ring-spark.svg`), splash: false },
    ];

    await showBoard(page, brandMarksHtml(marks));
    // INTENT: Every mark draft at every size, dark and light, sidebar lockup and browser tab.
    await captureShot(page, `${key}-marks.png`, { fullPage: false, scrollToSelector: '#board' });

    const hero = dataUri(repoPath('assets/brand/concepts/persona-forge/social-ready/persona-forge-option-e-social.jpg'), 'image/jpeg');
    const avatar = dataUri(repoPath('assets/brand/concepts/persona-forge/avatar-options/persona-forge-option-e-avatar.png'), 'image/png');
    await showBoard(page, brandContextHtml(marks, hero, avatar));
    // INTENT: Hero art in its sanctioned places — README/social banner and the startup state per mark.
    await captureShot(page, `${key}-context.png`, { fullPage: false, scrollToSelector: '#board' });
}
