# Plan — hermes TTS integration: OpenAI `/v1/audio/speech` endpoint (and the streaming/Deliverable-B decision)

Status: **research complete; decision made; implementation pending.**
Owner context: this supersedes the open question in `../features/streaming-vocoder.md` about whether to build
Deliverable B (pipelined vocoder overlap). The answer is **no — there is no consumer for streaming**;
the real integration work is a batch OpenAI-compatible endpoint.

## The question this answers

Should persona-forge invest in streaming (Deliverable A already shipped) and pipelined overlap
(Deliverable B, gated on the Task 3 measurement)? The deciding factor is what the actual consumer —
the **hermes-agent** ("Iris") gateway on docker-agent — can consume.

## What hermes-agent is and how it does TTS

- Image: `nousresearch/hermes-agent` (the NousResearch Hermes agent). Source on docker-agent at
  `~/.hermes/hermes-agent/`; TTS implementation in `tools/tts_tool.py`; feature doc
  `website/docs/user-guide/features/tts.md`.
- Ten built-in TTS providers: edge (default), elevenlabs, openai, minimax, mistral, gemini, xai,
  neutts, kittentts, piper. Plus **custom command providers** (`type: command`).
- **Delivery is always a complete audio file.** Per the feature doc: Telegram = Opus `.ogg` voice
  bubble, Discord = Opus/MP3, WhatsApp = MP3 attachment, CLI = saved `.mp3`. There is no real-time
  playback channel on the messaging platforms; the clip is synthesized in full, then sent.
- The **`openai` provider** (`tts_tool.py` ~line 1022) points the OpenAI SDK at a configurable
  `base_url` (`tts.openai.base_url`), calls `/v1/audio/speech`, and finalizes with
  `response.stream_to_file(output_path)` — i.e. it writes the **whole file**. "Streaming" here is just
  the SDK's chunked download to disk, not real-time playback.
- **Custom command providers** write the input text to a temp file and run a shell command that
  **"must produce the audio file at the expected path."** Strictly batch, file-output.

## How persona-forge is currently wired into hermes (verified 2026-06-30)

Active config: `~/.hermes-gateway/config.yaml`, `tts.provider: iris-mlx`. `iris-mlx` is a
`type: command` provider (`output_format: mp3`, `timeout: 300`) whose shell command does:

1. **Primary** — `POST http://192.168.2.126:8317/v1/audio/speech` (MLX `Qwen3-TTS-12Hz-1.7B-Base-8bit`
   on Nick's Mac), OpenAI-compatible payload `{model, input, ref_audio, ref_text, response_format,
   temperature, top_p, top_k}`, `-o {output_path}`, 10 s fail-fast.
2. **Fallback** — `POST http://persona-forge:8318/generate` (this repo's CPU OpenVINO service, **batch**),
   payload `{text, language}`, `-o {output_path}`, 270 s.
3. Both arms produce a complete **MP3 file**. Both fail → `FATAL: BOTH_TTS_PROVIDERS_FAILED`.

So today hermes consumes persona-forge **only in batch mode**, via `/generate`, and the fallback is the one
remaining arm that does not match the primary's OpenAI schema.

### Reference-voice reality (verified 2026-06-30) — why `ref_audio`/`ref_text` stay server-side

The primary's `ref_audio` is a **hardcoded Mac-local filesystem path**
`"/Users/nick/AI/mlx-audio/reference/voice_iris_a.wav"` with `ref_text` = our exact baked-in
`REF_TEXT` ("Welcome to Rosies…"). The CPU fallback payload is `{text, language:"english"}` — it
**does not send `ref_audio`/`ref_text` at all**. Implications:

- That path exists only on the Mac; our container cannot read it, and opening arbitrary host paths
  would be unsafe. Honoring `ref_audio` as sent would *break* (file-not-found), not help.
- The voices already match: our server-side `REF_AUDIO=/voice/voice_A.wav` is the same Iris persona
  as `voice_iris_a.wav`, and the `ref_text` is identical.

**Decision (2026-06-30):** keep the voice **server-side**. The `/v1/audio/speech` endpoint accepts
`voice`/`ref_audio`/`ref_text` for schema parity but ignores them. A real per-request voice would
require a *safe* input channel (base64 audio or a container-internal/mounted voices dir — never a host
path), per-request `create_voice_clone_prompt` with caching, verification that it works under
`OPENVINO_RELEASE_TORCH=1`, **and** a hermes-side change to actually send usable ref data. Deferred to
future work (Nick has ideas); not in scope for this PR.

## Decision

1. **Deliverable A (streaming TTFB):** keep as-is. It is implemented, parity-validated, opt-in per
   endpoint, and memory-neutral. It has **no consumer today** but stays as a dormant capability for any
   future real-time channel (e.g. live voice calls). Do not remove; do not invest further.
2. **Deliverable B (pipelined overlap):** **do not build.** Task 3 showed it is technically possible
   (2 idle cores) but its only payoff is recovering streaming's 23–25% wall-time penalty — and nothing
   consumes streaming. For producing a complete file, batch is already the fast path. The time-boxed
   spike is therefore moot. Recorded as GO-but-no-consumer in `../benchmarks/OPENVINO_RESULTS.md` / `../resolved/HANDOFF_container_image.md`.
3. **Actual work:** add an **OpenAI-compatible `/v1/audio/speech` endpoint** so the CPU service is a
   schema-identical drop-in for the MLX primary, replacing the bespoke `/generate {text,language}`
   fallback. This is higher value and lower risk than B.

## Implementation plan — OpenAI `/v1/audio/speech` endpoint

Add to `app_api.py` (public proxy), proxying the existing worker `/infer`; keep `/generate`,
`/generate/stream`, and `/health` unchanged.

Request (accept the OpenAI core plus the MLX primary's extensions so both arms match):

```json
POST /v1/audio/speech
{
  "model": "<ignored or echoed>",
  "input": "text to speak",            // required; maps to worker `text`
  "response_format": "mp3",            // mp3 (default) | wav | opus; maps to output encoding
  "voice": "<optional>",               // OpenAI field; our voice is server-side ref by default
  "ref_audio": "<optional>",           // MLX extension; accept + ignore unless we add ref override
  "ref_text": "<optional>",
  "temperature": 0.7, "top_p": 0.95, "top_k": 40   // optional sampling passthrough
}
→ 200, body = audio bytes, Content-Type per response_format (audio/mpeg, audio/wav, audio/ogg)
```

Behavior:
- `input` empty/missing → 400, OpenAI-style error JSON.
- Map `input` → worker `text`, `language` default `"english"` (or accept optional `language`).
- `response_format` → existing encoder path (mp3 today; add wav/opus if not present).
- Reference voice stays server-side default; `ref_audio`/`ref_text` accepted for schema parity but
  may be no-ops until per-request ref override is implemented (note as a follow-up).
- Reuse the same batch `/infer` worker call; no new model code, no streaming.

Tests (`tests/test_app_api.py`): valid request returns audio + correct Content-Type; missing `input`
→ 400; `response_format` variants; existing endpoints untouched.

## Hermes-side change (out of this repo, document only)

Once the endpoint exists, simplify the `iris-mlx` command's fallback arm to call
`POST http://persona-forge:8318/v1/audio/speech` with the **same payload as the primary** (model/input/
ref_*/response_format/sampling), so primary and fallback are schema-identical. Optionally migrate to a
native `openai` provider with `base_url: http://persona-forge:8318/v1` if hermes provider-fallback chaining
is desired (currently the failover lives inside the custom command, which is fine to keep).

## Next steps

1. Implement `/v1/audio/speech` in `app_api.py` + tests; rebuild image; smoke test on docker-agent.
2. Finalize the streaming-validation PR (Tasks 4 listening, 5 Compose/import smoke, 6 docs/PR) —
   independent of this endpoint; A ships as a dormant capability.
3. Update `~/.hermes-gateway/config.yaml` fallback arm to the new endpoint (host-side, with Nick).
