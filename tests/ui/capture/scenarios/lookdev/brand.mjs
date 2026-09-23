// SCENARIO INTENT: Signal Crucible brand board. Shows the selected SVG set at
// production sizes and the selected hero family in social, startup, and avatar contexts.
// Plan: luminous_instrument_redesign.md "P0" and owner D7 refinement.
import { captureShot } from '../../harness/shot.mjs';
import { brandContextHtml, brandMarksHtml, dataUri, repoPath, showBoard } from '../../lookdev/pages.mjs';

const key = 'lookdev-brand';
export const LOOKDEV_BRAND_OUTPUTS = [`${key}--neutral--marks.png`, `${key}--neutral--context.png`];
const FINAL = 'assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible';

export default async function ({ page }) {
    const svg = (path) => dataUri(repoPath(path), 'image/svg+xml');
    const marks = [
        { name: 'Current · stock Vite favicon', uri: svg('frontend/public/favicon.svg'), flag: true },
        { name: 'Signal Crucible · full + compact', uri: svg(`${FINAL}/svg/mark.svg`), smallUri: svg(`${FINAL}/svg/mark-small.svg`) },
        { name: 'Signal Crucible · compact mark', uri: svg(`${FINAL}/svg/mark-small.svg`), splash: false },
        { name: 'Signal Crucible · favicon', uri: svg(`${FINAL}/svg/favicon.svg`), splash: false },
    ];

    await showBoard(page, brandMarksHtml(marks));
    // INTENT: Verify full, compact, and favicon geometry on light/dark chrome and at small sizes.
    await captureShot(page, `${key}-marks.png`, { fullPage: false, scrollToSelector: '#board' });

    const hero = dataUri(repoPath(`${FINAL}/github-social.jpg`), 'image/jpeg');
    const avatar = dataUri(repoPath(`${FINAL}/avatar-study.png`), 'image/png');
    await showBoard(page, brandContextHtml(marks, hero, avatar));
    // INTENT: Verify selected artwork in social, startup, and square contexts.
    await captureShot(page, `${key}-context.png`, { fullPage: false, scrollToSelector: '#board' });
}
