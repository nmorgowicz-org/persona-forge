# Hermes v0.20.0 Full-Duplex TTS Integration

Date: 2026-08-10
Status: Done — full-duplex barge-in verified live on 2026-08-12 (interrupted mid-reply, playback stopped instantly)

## Objective

Integrate qwen3-tts-openvino (Pocket-TTS backend with Iris voice clone) into Hermes v0.20.0's streaming TTS + full-duplex barge-in pipeline.

## Integration Architecture

**Hermes TTS pipeline:**
- Token → sentence → audio via `StreamingTTSProvider` + `SentenceChunker`
- Desktop uses WebSocket `/api/audio/speak-stream` for per-reply streaming
- Barge-in: full-duplex, mic always live; interruption stops TTS and transcribes
- `voice.barge_in=true`, `voice.barge_in_threshold_multiplier=3.0`, `voice.barge_in_grace_seconds=0.5`

**Our position in the stack:**
- Hermes calls our `/v1/audio/speech` endpoint per sentence (sync path, not token-streaming)
- Hermes handles streaming UX, barge-in, and interruption internally
- We expose a proper OpenAI-compatible endpoint that Hermes already knows how to call
- No custom Hermes provider or code changes required

**Why sync path is fine:**
- Pocket-TTS generates full audio per sentence before responding (inference-bound, not network-bound)
- Hermes SentenceChunker already splits at `.!?` boundaries (20-100 chars typically)
- Each sentence synthesizes independently; Hermes plays as each completes
- This gives the same "streaming" UX without needing token-level streaming

## Endpoint Changes Made

### 1. Accept both `voice` and `voice_id` params

OpenAI SDK sends `voice`; our convention uses `voice_id`. Fixed in `/v1/audio/speech`:

```python
# OpenAI SDK sends "voice", our internal convention uses "voice_id" — accept both.
voice_id = (data.get("voice_id") or data.get("voice") or "").strip() or None
```

Also extended `_resolve_builtin_voice` to check the `voice` param for `pocket:` prefixed builtins.

### 2. Added PCM output support

Hermes streaming expects raw int16 LE mono PCM at 24kHz. Added `pcm` to supported formats:

```python
_SUPPORTED_FORMATS = {
    "mp3": ("MP3", "audio/mpeg"),
    "wav": ("WAV", "audio/wav"),
    "pcm": ("RAW", "audio/pcm"),
}
```

PCM encoding in `_encode()`:
- Converts float32 [-1,1] to int16
- Returns raw bytes (no header)
- Media type: `audio/pcm`

### 3. Default format note

Current default: `mp3` (via `_canonical_format`). For Hermes integration, Hermes will explicitly request `wav` or `pcm` based on its temp file convention.

## Test Results (2026-08-10)

All tests against Iris voice clone `vd_000000000001`:

1. **voice_id + WAV:**
   - Request: `{"text": "...", "voice_id": "vd_000000000001", "response_format": "wav"}`
   - Result: 157KB WAV, 24kHz/16bit/mono ✓

2. **voice param + WAV (Hermes shape):**
   - Request: `{"input": "...", "voice": "vd_000000000001", "response_format": "wav"}`
   - Result: 192KB WAV, 24kHz/16bit/mono ✓

3. **voice param + PCM (Hermes streaming shape):**
   - Request: `{"input": "...", "voice": "vd_000000000001", "response_format": "pcm"}`
   - Result: 134KB raw int16 PCM data, correct binary format ✓

**Built-in voices:** Currently broken on `feature/voice-style-foundation` branch due to Pocket-TTS API mismatch (`TTSModel.export_model_state` missing). Not relevant for our Hermes integration — we use Iris voice clone.

## Gateway Iris Configuration

### Recommended: OpenAI-compatible provider

Hermes's built-in OpenAI TTS path is tested and reliable. Our endpoint is fully compatible:

```yaml
tts:
  provider: openai
  openai:
    base_url: http://qwen3-tts:8318/v1
    model: qwen3-tts-pocket
    voice: vd_000000000001   # Iris voice clone
    speed: 1.0

voice:
  barge_in: true
  barge_in_threshold_multiplier: 3.0
  barge_in_grace_seconds: 0.5
  thinking_sound: true
```

**How Hermes will call us:**
```
POST /v1/audio/speech
{
  "model": "qwen3-tts-pocket",
  "voice": "vd_000000000001",
  "input": "This is a sentence from Hermes.",
  "response_format": "wav"   # or "pcm" depending on streaming path
}
```

### Alternative: Custom command provider

If Hermes OpenAI path doesn't behave as expected, we can fall back to a command-type provider:

```yaml
tts:
  provider: iris-qwen3

providers:
  iris-qwen3:
    type: command
    timeout: 120
    max_text_length: 8000
    command: |
      curl -s -X POST http://qwen3-tts:8318/v1/audio/speech \
        -H "Content-Type: application/json" \
        -d "{\"input\": {input_text}, \"voice\": \"vd_000000000001\", \"model\": \"qwen3-tts-pocket\", \"response_format\": \"wav\"}"
```

## Timeout and Max Text Length

### Max text length: 8000 chars

Rationale:
- Pocket-TTS handles up to several thousand characters comfortably
- Hermes SentenceChunker already splits at natural sentence boundaries
- 8000 is a safety cap that lets Hermes send a couple of sentences at once
- Typical sentence: 20-100 words; even a long paragraph rarely exceeds this

### Timeout: 120 seconds

Rationale:
- Typical sentence generation: 2-10 seconds on CPU
- Edge case (8000 chars): maybe 20-40 seconds
- 120 seconds provides headroom for pathological cases
- OpenAI SDK default is 30s; we should configure higher via `tts.openai.timeout` if needed

## MLX Audio / MP3 Removal

### MLX removal status: CLEAN

Our Dockerfile has **zero MLX dependencies**:
- Pure PyTorch CPU + Pocket-TTS runtime
- Native Linux tools: sox, ffmpeg, soundfile
- No mlx-audio references anywhere

### MP3 removal from full-duplex path: HANDLED

- Our `/v1/audio/speech` supports `pcm`, `wav`, `mp3` formats
- Hermes will explicitly request `pcm` or `wav` — we never default to MP3 in streaming
- Default format remains `mp3` for backward compatibility, but Hermes always specifies format
- PCM output is raw int16 LE mono at 24kHz — exactly what Hermes expects

## Docker Configuration

### Build command

```bash
cd /home/nick/projects/qwen3-tts-openvino
docker compose build qwen3-tts
```

### Start with dev mounts

```bash
cd /home/nick/docker
docker compose -f docker-compose.yml -f docker-compose.qwen3-tts-dev.yml up -d qwen3-tts
```

Dev overlay bind-mounts:
- `/home/nick/projects/qwen3-tts-openvino/src:/app/src:ro`
- `/home/nick/projects/qwen3-tts-openvino/frontend/dist:/app/frontend/dist:ro`
- `/var/data/autopirate/qwen3-tts-new/:/voice` (voice foundation)
- `/var/data/autopirate/qwen3-tts-new/segments/:/segments` (segment library)
- `/var/data/autopirate/qwen3-tts/:/voices` (voice library)

### Voice foundation paths

- Iris reference: `/var/data/autopirate/qwen3-tts-new/reference_voice_A.wav`
- Segment library: `/var/data/autopirate/qwen3-tts-new/segments/`
- Voice library: `/var/data/autopirate/qwen3-tts/` (persistent)
- DO NOT DELETE — irreplaceable from backup, forms Iris's TTS identity

## Next Steps

1. [DONE] Build and deploy qwen3-tts container with Hermes-compatible changes
2. [DONE] Test endpoint with voice_id, voice param, WAV and PCM formats
3. [DONE] Apply Gateway Iris config (OpenAI provider shape) — `~/.hermes-gateway/config.yaml` on docker-agent, `tts.openai.base_url` → persona-forge's `/v1/audio/speech`
4. [DONE] Test full Hermes integration (LLM response → TTS → barge-in) — verified live 2026-08-12: interrupted a reply mid-playback, TTS stopped instantly
5. [NOT DONE — not blocking] Verify PCM output sample rate matches Hermes expectation (24kHz) — never explicitly measured; live barge-in test worked, so functionally fine, but not formally confirmed
6. [NOT DONE — not blocking] Monitor latency for longer sentences (4000-8000 chars) — not exercised by tonight's test

## Known Issues

- Built-in Pocket-TTS voices (`pocket:vera`, etc.) broken on this branch due to `export_model_state` API change. Not relevant — we use Iris clone.
- Voice cloning requires HF_TOKEN for kyutai/pocket-tts access. Currently works because Pocket-TTS runtime loaded successfully.
