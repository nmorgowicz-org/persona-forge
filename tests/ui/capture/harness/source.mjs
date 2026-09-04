// Runtime-source selection for capture scenarios.
// Ported from local-llm-foundry's tests/ui/capture/harness/source.mjs, then
// redefined for persona-forge's own backends (fake/real-local/remote instead
// of local-llamacpp/local-mlx).
import { gotoApp } from './browser.mjs';
import { startFakeServer, startRealServer } from './server.mjs';
import { REMOTE_SERVER } from './paths.mjs';

// A remote source attaches to an already-running container (e.g. docker-agent) instead of
// spawning its own process, so it owns no process to tear down — but scenarios still create
// real voices/segments in that container's persistent library. Snapshot what exists before the
// scenario runs and delete anything new afterward, so remote captures don't leave clutter behind
// for someone to clean up by hand.
async function fetchIds(baseURL, path, listKey, idKey) {
    const res = await fetch(`${baseURL}${path}`);
    if (!res.ok) return new Set();
    const body = await res.json();
    return new Set((body[listKey] || []).map((item) => item[idKey]));
}

export async function snapshotRemoteState(baseURL) {
    const [voiceIds, segmentIds] = await Promise.all([
        fetchIds(baseURL, '/voices', 'voices', 'voice_id'),
        fetchIds(baseURL, '/omnivoice/segments', 'segments', 'segment_id'),
    ]);
    return { voiceIds, segmentIds };
}

export async function cleanupRemoteState(baseURL, before) {
    const after = await snapshotRemoteState(baseURL);
    const newVoiceIds = [...after.voiceIds].filter((id) => !before.voiceIds.has(id));
    const newSegmentIds = [...after.segmentIds].filter((id) => !before.segmentIds.has(id));
    await Promise.all([
        ...newVoiceIds.map((id) =>
            fetch(`${baseURL}/voices/${id}`, { method: 'DELETE' }).catch((err) => {
                console.warn(`[CAPTURE] remote cleanup: failed to delete voice ${id}: ${err.message}`);
            }),
        ),
        ...newSegmentIds.map((id) =>
            fetch(`${baseURL}/omnivoice/segments/${id}`, { method: 'DELETE' }).catch((err) => {
                console.warn(`[CAPTURE] remote cleanup: failed to delete segment ${id}: ${err.message}`);
            }),
        ),
    ]);
    if (newVoiceIds.length || newSegmentIds.length) {
        console.log(
            `[CAPTURE] remote cleanup: removed ${newVoiceIds.length} voice(s), ${newSegmentIds.length} segment(s)`,
        );
    }
}

export const CAPTURE_SOURCES = Object.freeze(['fake', 'real-local', 'remote']);
const IMPLEMENTED_SOURCES = new Set(['fake', 'real-local', 'remote']);

function validateSource(source, origin) {
    if (!CAPTURE_SOURCES.includes(source)) {
        throw new Error(
            `[CAPTURE] Unknown source "${source}" from ${origin}. ` +
            `Choose one of: ${CAPTURE_SOURCES.join(', ')}.`,
        );
    }
    return source;
}

/**
 * Resolve the source using the documented precedence order:
 * force → CLI option → CAPTURE_SOURCE → scenario default → remote.
 */
export function resolveCaptureSource({
    force,
    source,
    envSource = process.env.CAPTURE_SOURCE,
    scenarioSource = 'remote',
} = {}) {
    if (force) return validateSource(force, 'scenario force');
    if (source) return validateSource(source, '--source');
    if (envSource) return validateSource(envSource, 'CAPTURE_SOURCE');
    if (scenarioSource) return validateSource(scenarioSource, 'scenario default');
    return 'remote';
}

/**
 * Connect a capture page to the selected runtime source and return a uniform
 * handle: { kind, baseURL, teardown }. For fake/real-local, teardown() stops
 * the spawned server; for remote it is a no-op (nothing was spawned).
 */
export async function connectSource(page, opts = {}) {
    const source = resolveCaptureSource(opts);
    if (!IMPLEMENTED_SOURCES.has(source)) {
        throw new Error(
            `[CAPTURE] Source "${source}" is not implemented. ` +
            `Use one of: ${[...IMPLEMENTED_SOURCES].join(', ')}.`,
        );
    }

    if (source === 'remote') {
        const baseURL = opts.remoteServer || REMOTE_SERVER;
        const before = await snapshotRemoteState(baseURL);
        await gotoApp(page, baseURL);
        return {
            kind: source,
            baseURL,
            async teardown() {
                // Remote attach owns no process, but scenarios may have created real voices/
                // segments in the remote container's persistent library — remove only what
                // this run added, leaving anything that was already there untouched.
                await cleanupRemoteState(baseURL, before);
            },
        };
    }

    const server = source === 'fake'
        ? await startFakeServer(opts.serverOptions)
        : await startRealServer(opts.serverOptions);
    await server.waitUntilHealthy();
    await gotoApp(page, server.url);
    return {
        kind: source,
        baseURL: server.url,
        async teardown() {
            server.stop();
        },
    };
}
