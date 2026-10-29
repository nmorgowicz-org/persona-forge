/**
 * Integrations snippets use PERSONA_FORGE_BASE_URL as the service origin. Resolve it in the
 * target language (not as a literal "$VARIABLE" in Python/JS) and append /v1 exactly once.
 */
export const BASE_URL_PLACEHOLDER = '$PERSONA_FORGE_BASE_URL'

/** Accept either the documented origin or a pasted SDK base ending in /v1. */
export function originOf(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, '').replace(/\/v1$/, '')
}

export function curlSnippet(voiceId: string | null, model?: string): string {
  // JSON quoting and POSIX shell quoting are separate layers. In particular an apostrophe
  // inside a JSON string must not terminate the shell's single-quoted request body.
  const body = JSON.stringify({
    ...(model ? { model } : {}),
    input: 'Hello from Hermes.',
    ...(voiceId !== null ? { voice_id: voiceId } : {}),
    response_format: 'mp3',
  }, null, 2).replace(/'/g, `'"'"'`)
  return `: "\${PERSONA_FORGE_BASE_URL:?Set PERSONA_FORGE_BASE_URL to the service origin.}"
base_url="$PERSONA_FORGE_BASE_URL"
while [ "\${base_url%/}" != "$base_url" ]; do base_url="\${base_url%/}"; done
base_url="\${base_url%/v1}"
curl -X POST "\${base_url}/v1/audio/speech" \\
  -H "Content-Type: application/json" \\
  -d '${body}' \\
  --output speech.mp3`
}

export function pythonSnippet(voiceId: string | null, model = 'persona-forge'): string {
  // A JSON string literal is also a Python string literal (only strings, never JSON
  // booleans/null). No raw interpolation of a voice ID or model into executable code.
  const modelLiteral = JSON.stringify(model)
  const request = voiceId === null
    // The high-level SDK method requires voice. Use its low-level request method to truly
    // omit the field, allowing the route's persisted default/runtime reference to apply.
    ? `# No explicit voice: let Persona Forge resolve its API default/runtime reference.
response = client.post(
    "/audio/speech",
    body={"model": ${modelLiteral}, "input": "Hello from Hermes."},
    cast_to=httpx.Response,
)
Path("speech.mp3").write_bytes(response.content)`
    : `response = client.audio.speech.create(
    model=${modelLiteral},
    voice=${JSON.stringify(voiceId)},
    input="Hello from Hermes.",
)
response.stream_to_file("speech.mp3")`
  return `import os
${voiceId === null ? 'from pathlib import Path\nimport httpx\n' : ''}from openai import OpenAI

base_url = os.environ["PERSONA_FORGE_BASE_URL"].rstrip("/")
if base_url.endswith("/v1"):
    base_url = base_url[:-3]
client = OpenAI(base_url=base_url + "/v1", api_key="not-needed")

${request}`
}

export function jsSnippet(voiceId: string | null, model = 'persona-forge'): string {
  const body = JSON.stringify({ model, ...(voiceId !== null ? { voice: voiceId } : {}), input: 'Hello from Hermes.' }, null, 2)
  const request = voiceId === null
    ? `// The high-level SDK requires voice; a low-level request can omit it for the API default.
const speech = await client.post("/audio/speech", {
  body: ${body},
  __binaryResponse: true,
});`
    : `const speech = await client.audio.speech.create(${body});`
  return `import OpenAI from "openai";
import { writeFile } from "node:fs/promises";

const baseURL = process.env.PERSONA_FORGE_BASE_URL;
if (!baseURL) throw new Error("Set PERSONA_FORGE_BASE_URL to the service origin.");
const client = new OpenAI({
  baseURL: baseURL.replace(/\\/+$/, "").replace(/\\/v1$/, "") + "/v1",
  apiKey: "not-needed",
});

${request}
await writeFile("speech.mp3", Buffer.from(await speech.arrayBuffer()));`
}
