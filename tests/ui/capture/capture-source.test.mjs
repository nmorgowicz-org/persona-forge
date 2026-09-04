// Rewrite of local-llm-foundry's tests/ui/capture/capture-platform.test.mjs
// per docs/plans/archive/screenshots/20260815-screenshot_and_docs_edit.md Step 1.15. That test
// exercised capturePlatformSkipReason (Apple-Silicon/rapid-preset gating),
// which has no persona-forge analogue. This tests resolveCaptureSource's
// precedence order (force -> --source -> CAPTURE_SOURCE env -> scenario
// default -> remote) and that an unimplemented source throws instead.
import assert from 'node:assert/strict';
import test from 'node:test';
import {
    CAPTURE_SOURCES,
    cleanupRemoteState,
    resolveCaptureSource,
    snapshotRemoteState,
} from './harness/source.mjs';

test('force wins over everything else', () => {
    assert.equal(
        resolveCaptureSource({
            force: 'fake',
            source: 'real-local',
            envSource: 'remote',
            scenarioSource: 'remote',
        }),
        'fake',
    );
});

test('--source wins over env and scenario default', () => {
    assert.equal(
        resolveCaptureSource({
            source: 'real-local',
            envSource: 'remote',
            scenarioSource: 'remote',
        }),
        'real-local',
    );
});

test('CAPTURE_SOURCE env wins over scenario default', () => {
    assert.equal(
        resolveCaptureSource({
            envSource: 'fake',
            scenarioSource: 'remote',
        }),
        'fake',
    );
});

test('scenario default is used when nothing else is set', () => {
    assert.equal(
        resolveCaptureSource({
            envSource: undefined,
            scenarioSource: 'fake',
        }),
        'fake',
    );
});

test('falls back to remote when nothing is set at all', () => {
    assert.equal(
        resolveCaptureSource({
            envSource: undefined,
            scenarioSource: undefined,
        }),
        'remote',
    );
});

test('rejects an unknown source at any precedence level', () => {
    assert.throws(
        () => resolveCaptureSource({ force: 'not-a-real-source' }),
        /Unknown source "not-a-real-source"/,
    );
});

test('CAPTURE_SOURCES lists the known source kinds', () => {
    assert.deepEqual(CAPTURE_SOURCES, ['fake', 'real-local', 'remote']);
});

// Remote-source cleanup: a remote attach owns no process, but scenarios can still create real
// voices/segments in the remote container's persistent library (this is what leaves a
// docker-agent container full of capture-run clutter). snapshotRemoteState/cleanupRemoteState
// diff before/after and delete only what a run added, never anything already there.
function fakeFetch(state) {
    return async (url, opts) => {
        const method = opts?.method || 'GET';
        if (url.endsWith('/voices') && method === 'GET') {
            return { ok: true, json: async () => ({ voices: [...state.voices].map((voice_id) => ({ voice_id })) }) };
        }
        if (url.endsWith('/omnivoice/segments') && method === 'GET') {
            return {
                ok: true,
                json: async () => ({ segments: [...state.segments].map((segment_id) => ({ segment_id })) }),
            };
        }
        const voiceMatch = url.match(/\/voices\/([^/]+)$/);
        if (voiceMatch && method === 'DELETE') {
            state.voices.delete(voiceMatch[1]);
            state.deletedVoices.push(voiceMatch[1]);
            return { ok: true, json: async () => ({ deleted: voiceMatch[1] }) };
        }
        const segMatch = url.match(/\/omnivoice\/segments\/([^/]+)$/);
        if (segMatch && method === 'DELETE') {
            state.segments.delete(segMatch[1]);
            state.deletedSegments.push(segMatch[1]);
            return { ok: true, json: async () => ({ deleted: true }) };
        }
        throw new Error(`fakeFetch: unhandled ${method} ${url}`);
    };
}

test('cleanupRemoteState deletes only voices/segments created during the run', async (t) => {
    const state = {
        voices: new Set(['vd_preexisting']),
        segments: new Set(['seg_preexisting']),
        deletedVoices: [],
        deletedSegments: [],
    };
    t.mock.method(globalThis, 'fetch', fakeFetch(state));

    const before = await snapshotRemoteState('http://remote');
    // Scenario runs and creates new state.
    state.voices.add('vd_created_by_scenario');
    state.segments.add('seg_created_by_scenario');

    await cleanupRemoteState('http://remote', before);

    assert.deepEqual(state.deletedVoices, ['vd_created_by_scenario']);
    assert.deepEqual(state.deletedSegments, ['seg_created_by_scenario']);
    assert.ok(state.voices.has('vd_preexisting'));
    assert.ok(state.segments.has('seg_preexisting'));
});

test('cleanupRemoteState is a no-op when nothing new was created', async (t) => {
    const state = {
        voices: new Set(['vd_preexisting']),
        segments: new Set(),
        deletedVoices: [],
        deletedSegments: [],
    };
    t.mock.method(globalThis, 'fetch', fakeFetch(state));

    const before = await snapshotRemoteState('http://remote');
    await cleanupRemoteState('http://remote', before);

    assert.deepEqual(state.deletedVoices, []);
    assert.deepEqual(state.deletedSegments, []);
});

test('snapshotRemoteState treats a failed fetch as an empty set rather than throwing', async (t) => {
    t.mock.method(globalThis, 'fetch', async () => ({ ok: false }));
    const snapshot = await snapshotRemoteState('http://remote');
    assert.deepEqual([...snapshot.voiceIds], []);
    assert.deepEqual([...snapshot.segmentIds], []);
});
