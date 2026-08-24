// Capture manifest report/lint. Ported from local-llm-foundry's
// tests/ui/capture/cli-manifest.mjs per
// docs/plans/archive/screenshots/20260815-screenshot_and_docs_edit.md Step 1.15, with the
// wizard-rapidmlx/wizard-llamacpp category-registration checks (a
// local-llm-foundry-specific concept with no persona-forge analogue)
// replaced by a scenario-file <-> registry parity check.
import fs from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join, relative } from 'path';
import { SCENARIOS } from './index.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SCENARIOS_DIR = join(__dirname, 'scenarios');

const CAPTURE_CALL = /\b(captureShot|captureElementScreenshot)\s*\(\s*page\s*,\s*(?:[a-zA-Z0-9_.]+\s*,\s*)?['"`]([^'"`]+)['"`]/;

function walk(dir) {
    const out = [];
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) out.push(...walk(full));
        else if (entry.name.endsWith('.mjs')) out.push(full);
    }
    return out;
}

function intentFor(lines, idx, scenarioIntent) {
    for (let i = idx - 1; i >= Math.max(0, idx - 5); i -= 1) {
        const line = lines[i].trim();
        if (line.startsWith('// INTENT:')) return line.replace('// INTENT:', '').trim();
        if (line.startsWith('//')) return line.replace(/^\/\/\s*/, '').trim();
        if (line !== '') break; // stop at first non-comment, non-blank line
    }
    return scenarioIntent || '(unannotated)';
}

function main() {
    const strict = process.argv.includes('--strict');
    const files = walk(SCENARIOS_DIR);
    let total = 0;
    let annotated = 0;
    const violations = [];

    if (strict && files.length !== Object.keys(SCENARIOS).length) {
        violations.push(
            `scenario file count (${files.length}) does not match SCENARIOS registry count (${Object.keys(SCENARIOS).length})`
        );
    }

    for (const file of files.sort()) {
        const text = fs.readFileSync(file, 'utf8');
        const lines = text.split('\n');
        const scenarioPath = relative(SCENARIOS_DIR, file);
        const scenarioIntent = text.match(/^\/\/ SCENARIO INTENT:\s*(.+)$/m)?.[1] || null;
        if (strict && !scenarioIntent) {
            violations.push(`${scenarioPath} is missing a "// SCENARIO INTENT:" header`);
        }

        const rows = [];
        lines.forEach((line, idx) => {
            const m = CAPTURE_CALL.exec(line);
            if (m) {
                const intent = intentFor(lines, idx, scenarioIntent);
                rows.push({ filename: m[2], intent });
                total += 1;
                if (intent !== '(unannotated)') annotated += 1;
                if (strict && intent === '(unannotated)') {
                    violations.push(`${scenarioPath}:${idx + 1} missing INTENT for ${m[2]}`);
                }
            }
        });
        if (rows.length === 0) continue;
        console.log(`\n${scenarioPath}`);
        for (const row of rows) {
            console.log(`  ${row.filename}\t${row.intent}`);
        }
    }

    console.log(`\n[CAPTURE MANIFEST] ${annotated}/${total} capture call sites have an INTENT comment.`);
    console.log(`[CAPTURE MANIFEST] ${files.length} scenario file(s), ${Object.keys(SCENARIOS).length} registry entries.`);
    if (strict && violations.length) {
        for (const violation of violations) console.error(`[CAPTURE MANIFEST] ${violation}`);
        process.exitCode = 1;
    }
}

main();
