#!/usr/bin/env node
// Capture harness entrypoint: registry, CLI, and orchestration.
// Ported from local-llm-foundry's tests/ui/capture/index.mjs, then adapted:
// - No RUNNING_PORT/spawnLlamaMonitor/seedConfig/cleanupServer/cleanupTempHome
//   process-spawn lifecycle. persona-forge instead resolves a runtime source
//   (fake/real-local/remote) via harness/source.mjs's connectSource().
// - No capturePlatformSkipReason (Rapid-MLX/Apple-Silicon gate) — persona-forge
//   has no equivalent hardware-dependent scenario class.
// - Flags trimmed to what applies here: --scenario, --list-scenarios,
//   --source, --help/-h. Dropped --chat-only/--gpu-only/--inference-only/
//   --no-attach/--close-up (local-llm-foundry chat/telemetry concepts).
//
// docs/plans/20260815-screenshot_and_docs_edit.md Step 1.10.
import { setArtifactCategory, setArtifactRuntime, DEFAULT_VIEWPORT } from './harness/paths.mjs';
import { connectSource, resolveCaptureSource, CAPTURE_SOURCES } from './harness/source.mjs';
import { launchBrowser } from './harness/browser.mjs';
import { cleanupFrames } from './harness/shot.mjs';
import { beginCaptureReceipt, finishCaptureReceipt, setCaptureDiagnostics } from './harness/receipt.mjs';

import health from './scenarios/core/health.mjs';
import home from './scenarios/core/home.mjs';
import generate from './scenarios/generate/generate.mjs';
import voiceDesignPanel from './scenarios/voice-design/panel.mjs';
import voiceDesignGenerate from './scenarios/voice-design/generate.mjs';
import voiceVariantList from './scenarios/voice-library/variant-list.mjs';
import voicePromoteVariant from './scenarios/voice-library/promote-variant.mjs';
import accentProjectGrouping from './scenarios/voice-library/project-grouping.mjs';
import voicesList from './scenarios/voice-library/list.mjs';
import alignmentCompare from './scenarios/prosody/alignment-compare.mjs';
import prosodyAdjustment from './scenarios/prosody/prosody-adjustment.mjs';
import segmentLibraryBrowse from './scenarios/stitch-studio/segment-library-browse.mjs';
import stitchAssembly from './scenarios/stitch-studio/assembly.mjs';
import omnivoiceAudition from './scenarios/omnivoice/audition.mjs';
import omnivoiceCandidates from './scenarios/omnivoice/candidates.mjs';
import omnivoiceAuditionGif from './scenarios/omnivoice/audition-gif.mjs';
import designToStitchGif from './scenarios/wizard/design-to-stitch-gif.mjs';
import heroSpeakFilled from './scenarios/hero/speak-filled.mjs';
import heroSpeakResult from './scenarios/hero/speak-result.mjs';
import heroVoiceDesign from './scenarios/hero/voice-design.mjs';
import heroLibrary from './scenarios/hero/library.mjs';

export const SCENARIOS = {
    health: {
        run: health,
        category: 'core',
        runtime: 'neutral',
        contract: {
            intent: 'Prove the service is up and reporting backend/model status.',
            expectedOutputs: ['health--neutral--health.png'],
        },
    },
    home: {
        run: home,
        category: 'core',
        runtime: 'neutral',
        contract: {
            intent: "Show the app's landing state before any interaction.",
            expectedOutputs: ['home--neutral--home.png'],
        },
    },
    'speak-generate': {
        run: generate,
        category: 'generate',
        runtime: 'pocket-tts',
        contract: {
            intent: 'Show the Speak tab before and after generating audio.',
            expectedOutputs: [
                'speak-generate--pocket-tts--before-generate.png',
                'speak-generate--pocket-tts--after-generate.png',
            ],
        },
    },
    'voice-design-panel': {
        run: voiceDesignPanel,
        category: 'voice-design',
        runtime: 'neutral',
        contract: {
            intent: 'Show the empty Voice Design panel.',
            expectedOutputs: ['voice-design-panel--neutral--panel-empty.png'],
        },
    },
    'voice-design-generate': {
        run: voiceDesignGenerate,
        category: 'voice-design',
        runtime: 'neutral',
        source: 'fake',
        contract: {
            intent: 'Fill in Voice Design fields and generate a result.',
            expectedOutputs: [
                'voice-design-generate--neutral--filled.png',
                'voice-design-generate--neutral--result.png',
            ],
        },
    },
    'voice-variant-list': {
        run: voiceVariantList,
        category: 'voice-library',
        runtime: 'neutral',
        source: 'fake',
        contract: {
            intent: 'Show the voice library variant list.',
            expectedOutputs: ['voice-variant-list--neutral--variant-list.png'],
        },
    },
    'voice-promote-variant': {
        run: voicePromoteVariant,
        category: 'voice-library',
        runtime: 'neutral',
        source: 'fake',
        contract: {
            intent: 'Promote a non-default voice variant to default.',
            expectedOutputs: [
                'voice-promote-variant--neutral--promote-before.png',
                'voice-promote-variant--neutral--promote-after.png',
            ],
        },
    },
    'accent-project-grouping': {
        run: accentProjectGrouping,
        category: 'voice-library',
        runtime: 'neutral',
        contract: {
            intent: 'Show accent voices grouped by project.',
            expectedOutputs: ['accent-project-grouping--neutral--project-grouping.png'],
        },
    },
    'voices-list': {
        run: voicesList,
        category: 'voice-library',
        runtime: 'neutral',
        contract: {
            intent: 'Generate a new voice, then show it appear in the library list.',
            expectedOutputs: ['voices-list--neutral--list.png'],
        },
    },
    'alignment-compare': {
        run: alignmentCompare,
        category: 'prosody',
        runtime: 'pocket-tts',
        contract: {
            intent: 'Show the prosody alignment comparison view.',
            expectedOutputs: ['alignment-compare--pocket-tts--alignment-compare.png'],
        },
    },
    'prosody-adjustment': {
        run: prosodyAdjustment,
        category: 'prosody',
        runtime: 'pocket-tts',
        contract: {
            intent: 'Showcase the prosody adjustment feature — Precise mode, Calm preset, with pause markers on the adjusted waveform.',
            expectedOutputs: [
                'prosody-adjustment--pocket-tts--voice-library.png',
                'prosody-adjustment--pocket-tts--settings-open.png',
                'prosody-adjustment--pocket-tts--preset-selected.png',
                'prosody-adjustment--pocket-tts--calm-adjusted.png',
            ],
        },
    },
    'segment-library-browse': {
        run: segmentLibraryBrowse,
        category: 'stitch-studio',
        runtime: 'neutral',
        contract: {
            intent: 'Browse the segment library picker in Stitch Studio.',
            expectedOutputs: ['segment-library-browse--neutral--segment-library-browse.png'],
        },
    },
    'stitch-assembly': {
        run: stitchAssembly,
        category: 'stitch-studio',
        runtime: 'neutral',
        contract: {
            intent: 'Assemble segments into a stitched clip.',
            expectedOutputs: ['stitch-assembly--neutral--assembly.png'],
        },
    },
    'omnivoice-audition': {
        run: omnivoiceAudition,
        category: 'omnivoice',
        runtime: 'omnivoice',
        source: 'fake',
        contract: {
            intent: 'Drive an OmniVoice audition and stitch to a result.',
            expectedOutputs: [
                'omnivoice-audition--omnivoice--audition-candidates.png',
                'omnivoice-audition--omnivoice--audition-result.png',
            ],
        },
    },
    'omnivoice-candidates': {
        run: omnivoiceCandidates,
        category: 'omnivoice',
        runtime: 'omnivoice',
        source: 'fake',
        contract: {
            intent: 'Show OmniVoice advanced candidates-per-segment control in use.',
            expectedOutputs: ['omnivoice-candidates--omnivoice--persona-forge-candidates.png'],
        },
    },
    'omnivoice-audition-gif': {
        run: omnivoiceAuditionGif,
        category: 'omnivoice',
        runtime: 'omnivoice',
        source: 'fake',
        contract: {
            intent: 'Animate an OmniVoice audition run as a GIF.',
            expectedOutputs: ['omnivoice-audition-gif--omnivoice--audition.gif'],
        },
    },
    'design-to-stitch-gif': {
        run: designToStitchGif,
        category: 'wizard',
        runtime: 'pocket-tts',
        source: 'fake',
        contract: {
            intent: 'Animate the end-to-end design-to-stitch wizard flow as a GIF.',
            expectedOutputs: ['design-to-stitch-gif--pocket-tts--design-to-stitch.gif'],
        },
    },
    'hero-speak-filled': {
        run: heroSpeakFilled,
        category: 'hero',
        runtime: 'pocket-tts',
        contract: {
            intent: 'Hero candidate — the Speak page as a first-time visitor sees it, text entered.',
            expectedOutputs: ['hero-speak-filled--pocket-tts--speak.png'],
        },
    },
    'hero-speak-result': {
        run: heroSpeakResult,
        category: 'hero',
        runtime: 'pocket-tts',
        contract: {
            intent: 'Hero candidate — the Speak page after a real generation, waveform visible.',
            expectedOutputs: ['hero-speak-result--pocket-tts--speak.png'],
        },
    },
    'hero-voice-design': {
        run: heroVoiceDesign,
        category: 'hero',
        runtime: 'neutral',
        contract: {
            intent: 'Hero candidate — the Voice Design trait-chip grid.',
            expectedOutputs: ['hero-voice-design--neutral--panel.png'],
        },
    },
    'hero-library': {
        run: heroLibrary,
        category: 'hero',
        runtime: 'neutral',
        contract: {
            intent: 'Hero candidate — the Voice Library with prosody fingerprints.',
            expectedOutputs: ['hero-library--neutral--panel.png'],
        },
    },
};

function printUsage() {
    console.log(`Usage: node tests/ui/capture/index.mjs [options]

Options:
  --scenario <key>     Run a single scenario by key
  --list-scenarios      List all registered scenario keys
  --source <kind>       Force a runtime source (${CAPTURE_SOURCES.join(', ')})
  --help, -h             Show this help

Scenarios:
${Object.keys(SCENARIOS).map((key) => `  ${key}`).join('\n')}
`);
}

export function parseArgs(argv) {
    const options = { scenario: null, listScenarios: false, source: null, help: false };
    for (let i = 0; i < argv.length; i += 1) {
        const arg = argv[i];
        switch (arg) {
            case '--scenario':
                options.scenario = argv[++i];
                break;
            case '--list-scenarios':
                options.listScenarios = true;
                break;
            case '--source':
                options.source = argv[++i];
                break;
            case '--help':
            case '-h':
                options.help = true;
                break;
            default:
                throw new Error(`Unknown argument: ${arg}`);
        }
    }
    return options;
}

export async function runCli({ scenario, source } = {}) {
    const key = scenario;
    const entry = SCENARIOS[key];
    if (!entry) {
        throw new Error(`Unknown scenario "${key}". Known scenarios: ${Object.keys(SCENARIOS).join(', ')}`);
    }

    setArtifactCategory(entry.category);
    setArtifactRuntime(key, entry.runtime);
    beginCaptureReceipt({ ...entry.contract, scenario: key, category: entry.category, runtime: entry.runtime });

    let browser;
    let sourceHandle;
    try {
        const launched = await launchBrowser(DEFAULT_VIEWPORT);
        browser = launched.browser;
        const { page } = launched;

        sourceHandle = await connectSource(page, { source, scenarioSource: entry.source });
        setCaptureDiagnostics({ source: sourceHandle.kind });

        await entry.run({ page, baseURL: sourceHandle.baseURL }, {});

        return finishCaptureReceipt();
    } finally {
        if (browser) await browser.close();
        if (sourceHandle) await sourceHandle.teardown();
        cleanupFrames();
    }
}

async function main() {
    const options = parseArgs(process.argv.slice(2));

    if (options.help) {
        printUsage();
        return;
    }

    if (options.listScenarios) {
        for (const key of Object.keys(SCENARIOS)) console.log(key);
        return;
    }

    if (options.source) resolveCaptureSource({ source: options.source });

    if (!options.scenario) {
        printUsage();
        throw new Error('--scenario <key> is required');
    }

    const receipt = await runCli({ scenario: options.scenario, source: options.source });
    console.log(`[CAPTURE] Receipt: ${JSON.stringify(receipt, null, 2)}`);
}

import { fileURLToPath } from 'node:url';
if (fileURLToPath(import.meta.url) === process.argv[1]) {
    main().catch((err) => {
        console.error(err);
        process.exit(1);
    });
}
