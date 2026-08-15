// Runtime-source selection for capture scenarios.
// Ported from local-llm-foundry's tests/ui/capture/harness/source.mjs, then
// redefined for persona-forge's own backends (fake/real-local/remote instead
// of local-llamacpp/local-mlx).
import { gotoApp } from './browser.mjs';
import { startFakeServer, startRealServer } from './server.mjs';
import { REMOTE_SERVER } from './paths.mjs';

export const CAPTURE_SOURCES = Object.freeze(['fake', 'real-local', 'remote', 'auto']);
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
        await gotoApp(page, baseURL);
        return {
            kind: source,
            baseURL,
            async teardown() {
                // Remote attach owns no process.
            },
        };
    }

    const server = source === 'fake'
        ? startFakeServer(opts.serverOptions)
        : startRealServer(opts.serverOptions);
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
