import assert from 'node:assert/strict'
import { execFileSync, spawnSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { curlSnippet, jsSnippet, originOf, pythonSnippet } from '../../../frontend/src/lib/apiSnippets.ts'

// Run the generated programs, substituting only the SDK/HTTP boundary. No service or model.
const pythonHarness = `import json, sys, types
class Speech:
    def create(self, *, model, voice, input):
        self.kwargs = dict(model=model, voice=voice, input=input)
        return self
    def stream_to_file(self, filename):
        print(json.dumps(dict(base_url=self.base_url, request=self.kwargs, output=filename)))
class OpenAI:
    def __init__(self, **kwargs):
        speech = Speech()
        speech.base_url = kwargs['base_url']
        self.audio = types.SimpleNamespace(speech=speech)
    def post(self, path, *, body, cast_to):
        assert path == '/audio/speech'
        print(json.dumps(dict(base_url=self.audio.speech.base_url, request=body)))
        return types.SimpleNamespace(content=bytes([1, 2, 3]))
sys.modules['httpx'] = types.SimpleNamespace(Response=object)
sys.modules['openai'] = types.SimpleNamespace(OpenAI=OpenAI)
exec(sys.argv[1])
`
const jsSdk = `export default class OpenAI {
  constructor(options) {
    const create = async (request) => {
      console.log(JSON.stringify({ base_url: options.baseURL, request }));
      return { arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer };
    };
    this.audio = { speech: { create: async (request) => {
      if (!Object.hasOwn(request, "voice")) throw new Error("SDK requires voice");
      return create(request);
    } } };
    this.post = async (path, request) => {
      if (path !== "/audio/speech" || request.__binaryResponse !== true) throw new Error("bad SDK request");
      return create(request.body);
    };
  }
}
`
function withDirectory(fn) {
  const directory = mkdtempSync(join(tmpdir(), 'persona-forge-snippets-'))
  try { return fn(directory) } finally { rmSync(directory, { recursive: true, force: true }) }
}
function runPython(snippet, baseUrl) {
  return withDirectory((directory) => JSON.parse(execFileSync('python3', ['-c', pythonHarness, snippet], {
    cwd: directory, env: { ...process.env, PERSONA_FORGE_BASE_URL: baseUrl }, encoding: 'utf8',
  })))
}
function runJs(snippet, baseUrl) {
  return withDirectory((directory) => {
    writeFileSync(join(directory, 'sdk.mjs'), jsSdk)
    writeFileSync(join(directory, 'snippet.mjs'), snippet.replace('from "openai"', 'from "./sdk.mjs"'))
    const result = JSON.parse(execFileSync(process.execPath, [join(directory, 'snippet.mjs')], {
      cwd: directory, env: { ...process.env, PERSONA_FORGE_BASE_URL: baseUrl }, encoding: 'utf8',
    }))
    assert.deepEqual([...readFileSync(join(directory, 'speech.mp3'))], [1, 2, 3])
    return result
  })
}
function runCurl(snippet, baseUrl) {
  return withDirectory((directory) => {
    // A fake curl records the real shell's argv, catching broken JSON and shell quoting.
    writeFileSync(join(directory, 'curl'), '#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n', { mode: 0o755 })
    const args = JSON.parse(execFileSync('sh', ['-c', snippet], {
      cwd: directory, env: { ...process.env, PATH: `${directory}:${process.env.PATH}`, PERSONA_FORGE_BASE_URL: baseUrl },
      encoding: 'utf8',
    }))
    return { url: args[args.indexOf('POST') + 1], request: JSON.parse(args[args.indexOf('-d') + 1]) }
  })
}

for (const [base, origin] of [
  ['http://localhost:8318', 'http://localhost:8318'],
  ['http://localhost:8318///', 'http://localhost:8318'],
  ['https://example.test/pf/v1', 'https://example.test/pf'],
  ['https://example.test/pf/v1/', 'https://example.test/pf'],
]) {
  test(`normalizes service origin ${base} without missing/doubled v1`, () => {
    assert.equal(originOf(base), origin)
    const shell = runCurl(curlSnippet('kitten2:Bruno', 'kitten2'), base)
    assert.equal(shell.url, `${origin}/v1/audio/speech`)
    for (const result of [runPython(pythonSnippet('kitten2:Bruno', 'kitten2'), base), runJs(jsSnippet('kitten2:Bruno', 'kitten2'), base)]) {
      assert.equal(result.base_url, `${origin}/v1`)
      assert.equal(result.request.voice, 'kitten2:Bruno')
      assert.equal(result.request.model, 'kitten2')
    }
    assert.equal(shell.request.voice_id, 'kitten2:Bruno')
    assert.equal(shell.request.model, 'kitten2')
  })
}

test('all snippets round-trip quotes, newlines, backslashes, Unicode, and shell metacharacters literally', () => {
  const voice = 'saved:\'"\\\n雪 $HOME `printf injected` $(printf injected)'
  const model = 'engine:\'"\\\n雪 $HOME `printf injected` $(printf injected)'
  const base = 'http://example.test/a $HOME `printf injected`/v1/'
  const shell = runCurl(curlSnippet(voice, model), base)
  assert.equal(shell.url, 'http://example.test/a $HOME `printf injected`/v1/audio/speech')
  assert.equal(shell.request.voice_id, voice)
  assert.equal(shell.request.model, model)
  for (const result of [runPython(pythonSnippet(voice, model), base), runJs(jsSnippet(voice, model), base)]) {
    assert.equal(result.request.voice, voice)
    assert.equal(result.request.model, model)
    assert.equal(result.base_url, 'http://example.test/a $HOME `printf injected`/v1')
  }
})

test('null voice truly omits voice so the route can use its runtime/API default', () => {
  const base = 'http://localhost:8318'
  const shell = runCurl(curlSnippet(null), base)
  assert.deepEqual(shell.request, { input: 'Hello from Hermes.', response_format: 'mp3' })
  for (const result of [runPython(pythonSnippet(null), base), runJs(jsSnippet(null), base)]) {
    assert.deepEqual(result.request, { model: 'persona-forge', input: 'Hello from Hermes.' })
  }
})

test('a saved voice with no pack model keeps the active-backend model semantics', () => {
  const base = 'http://localhost:8318'
  assert.equal(Object.hasOwn(runCurl(curlSnippet('vd_aabbccddeeff'), base).request, 'model'), false)
  for (const result of [runPython(pythonSnippet('vd_aabbccddeeff'), base), runJs(jsSnippet('vd_aabbccddeeff'), base)]) {
    assert.equal(result.request.voice, 'vd_aabbccddeeff')
    assert.equal(result.request.model, 'persona-forge')
  }
})

test('shell snippet fails actionably before curl when its base URL is unset', () => {
  withDirectory((directory) => {
    writeFileSync(join(directory, 'curl'), '#!/bin/sh\nprintf "curl should not run"\n', { mode: 0o755 })
    const env = { ...process.env, PATH: `${directory}:${process.env.PATH}` }
    delete env.PERSONA_FORGE_BASE_URL
    const result = spawnSync('sh', ['-c', curlSnippet(null)], { cwd: directory, env, encoding: 'utf8' })
    assert.notEqual(result.status, 0)
    assert.match(result.stderr, /PERSONA_FORGE_BASE_URL/)
    assert.equal(result.stdout, '')
  })
})
