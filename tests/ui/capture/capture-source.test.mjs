// Rewrite of local-llm-foundry's tests/ui/capture/capture-platform.test.mjs
// per docs/plans/20260815-screenshot_and_docs_edit.md Step 1.15. That test
// exercised capturePlatformSkipReason (Apple-Silicon/rapid-preset gating),
// which has no persona-forge analogue. This tests resolveCaptureSource's
// precedence order (force -> --source -> CAPTURE_SOURCE env -> scenario
// default -> remote) and that an unimplemented source throws instead.
import assert from 'node:assert/strict';
import test from 'node:test';
import { CAPTURE_SOURCES, resolveCaptureSource } from './harness/source.mjs';

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
    assert.deepEqual(CAPTURE_SOURCES, ['fake', 'real-local', 'remote', 'auto']);
});
