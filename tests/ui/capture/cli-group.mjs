// Run every scenario belonging to a registry category (== scenarios/<group>/
// directory name). Ported from local-llm-foundry's tests/ui/capture/cli-group.mjs
// per docs/plans/archive/screenshots/20260815-screenshot_and_docs_edit.md Step 1.15. Drops
// local-llm-foundry's TEMP_APP_CONFIG_DIR bootstrap (Go-binary-specific, no
// persona-forge analogue) and groups by SCENARIOS[key].category rather than by
// scanning the scenario directory tree, since persona-forge's registry keys
// don't always match their scenario file's stem (e.g. 'speak-generate' ->
// scenarios/generate/generate.mjs).
import { SCENARIOS, runCli } from './index.mjs';

function listGroups() {
    return [...new Set(Object.values(SCENARIOS).map((entry) => entry.category))].sort();
}

function scenariosInGroup(group) {
    return Object.keys(SCENARIOS).filter((key) => SCENARIOS[key].category === group).sort();
}

async function main() {
    const argv = process.argv.slice(2);
    const group = argv[0];
    const sourceFlagIdx = argv.indexOf('--source');
    const source = sourceFlagIdx >= 0 ? argv[sourceFlagIdx + 1] : undefined;

    if (!group || group === '--help' || group === '-h') {
        console.log('Usage: node capture/cli-group.mjs <group> [--source <kind>]');
        console.log('Groups:');
        for (const g of listGroups()) {
            console.log(`  ${g}  (${scenariosInGroup(g).join(', ')})`);
        }
        return;
    }

    const scenarios = scenariosInGroup(group);
    if (scenarios.length === 0) {
        throw new Error(`Unknown or empty group "${group}". Known groups: ${listGroups().join(', ')}`);
    }

    console.log(`[CAPTURE GROUP] Running ${scenarios.length} scenario(s) in group "${group}": ${scenarios.join(', ')}`);
    for (const scenario of scenarios) {
        console.log(`\n[CAPTURE GROUP] --- ${scenario} ---`);
        await runCli({ scenario, source });
    }
}

await main();
