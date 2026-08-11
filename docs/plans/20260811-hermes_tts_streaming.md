# Hermes v0.20.0 TTS Streaming Integration

## Executive Summary

Hermes Agent v0.20.0 (Herald Release, Aug 2026) introduced conversational voice mode with streaming TTS. For full-duplex voice mode, Hermes uses the OpenAI SDK's `with_streaming_response.create()` API against `/v1/audio/speech` with `response_format="pcm"`, expecting chunked HTTP transfer encoding so audio plays incrementally as it's synthesized rather than waiting for the complete response.

Our current `/v1/audio/speech` endpoint returns complete audio blobs (sync). We already have a working `/generate/stream` endpoint using Flask chunked streaming for Qwen3-TTS backends. The work needed: extend our OpenAI-compatible endpoint to stream audio chunks for Pocket-TTS (our primary backend), matching the format Hermes expects.

## OpenAI SDK Streaming Requirements (from Hermes analysis)

### HTTP Layer

From Hermes's `tools/tts_streaming.py` OpenAIStreamer:

```python
with client.audio.speech.with_streaming_response.create(
    model=model,
    voice=voice,
    input=text,
    response_format="pcm",
) as response:
    yield from response.iter_bytes()
```

Required behavior:
1. **Same endpoint**: `/v1/audio/speech` (POST) — Hermes does not expect a separate streaming endpoint
2. **Headers sent by client**: `Accept: application/octet-stream` (SDK adds this automatically)
3. **Response**: Chunked transfer encoding (Transfer-Encoding: chunked or streaming body)
4. **Consumption**: `StreamedBinaryAPIResponse.iter_bytes()` yields raw bytes as they arrive

### Audio Format

Hermes expects:
- **PCM format**: int16, little-endian, mono
- **Sample rate**: 24,000 Hz
- **Content-Type**: `audio/pcm` (our existing format for `response_format="pcm"`)

This matches our existing `/v1/audio/speech` PCM encoding logic (`app.py:160-167`).

### No special request parameter — streaming is the default

Unlike `/v1/chat/completions` which uses `stream: true`, the OpenAI TTS SDK's `with_streaming_response.create()` sends **no special header or parameter**. It just makes a normal POST to `/v1/audio/speech` and consumes the response body as a stream (`iter_bytes()`) instead of buffering it.

OpenAI's `/v1/audio/speech` **always streams** chunked audio. There is no toggle.

**Key design decision**: We must stream by default from `/v1/audio/speech`. No `stream` parameter, no separate endpoint.

Backward compatibility: The OpenAI SDK's standard `.create()` (without `with_streaming_response`) works identically against a streaming server — it just buffers the entire response client-side before returning it. Hermes's sync path uses exactly this pattern. Our own callers use `/generate`, not `/v1/audio/speech`. So always streaming is safe.

## Feasibility Assessment

### Pocket-TTS: ✅ Supports incremental generation

Pocket-TTS exposes `generate_audio_stream()` in its Python API:

```python
for chunk in model.generate_audio_stream(voice_state, text):
    # chunk: torch.Tensor with shape [samples]
```

This yields audio chunks as they're generated — exactly what we need. The function signature matches `generate_audio()`; no extra configuration required.

### Qwen3-TTS/OpenVINO: ✅ Already has streaming

We already have:
- `_run_generate_with_streaming()` in `model.py` with the `StreamingVocoderSession`
- `/generate/stream` endpoint that uses Flask chunked streaming
- FP32 OpenVINO vocoder for incremental decode

The existing streaming path is Qwen3-TTS-specific and requires the OpenVINO vocoder. For full Hermes support we need Pocket-TTS streaming (our default backend).

### Flask chunked streaming: ✅ Already proven

Our `/generate/stream` endpoint (`app.py:2555-2630`) demonstrates the pattern:

```python
def body():
    while True:
        kind, payload = events.get()
        if kind == "audio":
            yield payload
        # ...

return Response(
    body(),
    content_type="application/octet-stream",
    headers={...},
    direct_passthrough=True,
)
```

`direct_passthrough=True` is the key Flask/Werkzeug flag that enables chunked transfer encoding. Without it, Werkzeug buffers the entire generator into memory.

## Design

### Endpoint modifications

**Modify `/v1/audio/speech`** to return chunked audio stream by default when using Pocket-TTS backend with `pcm` format.

- Pocket-TTS + `pcm` format → chunked audio stream (Flask Response with generator + `direct_passthrough=True`)
- Other backends/formats (mp3, wav) or repair-enabled requests → existing batch behavior (complete blob)

**Request format (same as OpenAI spec, no extra parameter needed):**
```json
{
  "input": "Hello world",
  "model": "any",
  "voice": "default",
  "response_format": "pcm"
}
```

**Response format when streaming (PCM):**
- `Content-Type: audio/pcm`
- Raw int16 LE mono PCM chunks at 24kHz
- Chunked transfer encoding
- Each chunk: a block of PCM bytes (no framing, no SSE)

### Pocket-TTS streaming implementation

New function in `pocket_tts_runtime.py`:

```python
def generate_pocket_tts_stream(
    model: TTSModel,
    voice_state: dict[str, Any],
    text: str,
) -> Iterator[np.ndarray]:
    """Generate speech audio incrementally, yielding PCM float32 chunks."""
    for audio_chunk in model.generate_audio_stream(voice_state, text):
        yield audio_chunk.cpu().numpy().ravel()
```

New generator in `model.py`:

```python
def _run_generate_pocket_tts_stream(
    text: str,
    language: str,
    *,
    voice_id: str | None = None,
    seed_value=None,
):
    """Stream Pocket-TTS audio as int16 PCM chunks for Hermes."""
    from qwen3_tts import pocket_tts_runtime
    import numpy as np

    voice_state = pocket_tts_runtime.get_pocket_tts_voice_state(
        model, voice_id, voice_clone_prompt, REF_AUDIO,
    )
    for chunk in pocket_tts_runtime.generate_pocket_tts_stream(model, voice_state, text):
        # float32 [-1,1] → int16 LE
        pcm = np.clip(chunk, -1.0, 1.0)
        yield (pcm * 32767).astype(np.int16).tobytes()
```

### `/v1/audio/speech` endpoint changes

```python
@app.post("/v1/audio/speech")
def openai_audio_speech():
    # ... existing validation ...
    stream = data.get("stream", False)
    
    if stream:
        return _openai_audio_speech_streaming(...)
    else:
        # existing behavior
        wav, sr, job_id = model.executor.submit(...).result(...)
        audio, media_type = _encode(wav, sr, fmt)
        return Response(audio, content_type=media_type)
```

Streaming handler:

```python
def _openai_audio_speech_streaming(text, language, voice_id, fmt, **kwargs):
    if fmt != "pcm":
        return _openai_error("streaming only supported with response_format=pcm", 400)
    
    backend = model.TTS_BACKEND
    if backend == "pocket_tts":
        chunk_generator = _run_generate_pocket_tts_stream(...)
    elif backend in ("openvino", "pytorch"):
        chunk_generator = _run_generate_qwen3_stream(...)
    else:
        return _openai_error("streaming not supported for this backend", 501)
    
    def body():
        for pcm_chunk in chunk_generator:
            yield pcm_chunk
    
    return Response(
        body(),
        content_type="audio/pcm",
        headers={
            "X-Audio-Sample-Rate": "24000",
            "X-Audio-Channels": "1",
        },
        direct_passthrough=True,
    )
```

### Backends supported for streaming

| Backend | Status | Notes |
|---------|--------|-------|
| Pocket-TTS | New implementation | Uses `generate_audio_stream()` |
| Qwen3-TTS (OpenVINO) | Already works | Uses existing `/generate/stream` path via `_run_generate_with_streaming`; requires FP32 vocoder |
| Qwen3-TTS (PyTorch) | New implementation needed | PyTorch vocoder doesn't have chunked decode; would need to implement incremental vocoder decode or fall back to batch |

### Important: Gunicorn single-worker constraint

Our deployment uses `-w 1 -k gthread --threads 4`. Streaming via Flask generators works with this setup:
- Gunicorn single worker processes requests serially
- The streaming response's generator runs on the same thread as the handler
- While a stream is active, the worker is blocked serving that connection
- This is acceptable for Hermes's use case: one voice stream at a time

## Implementation Steps

1. **Add `generate_pocket_tts_stream()` to `pocket_tts_runtime.py`**
   - Thin wrapper around `TTSModel.generate_audio_stream()`
   - Yields float32 numpy arrays

2. **Add `_run_generate_pocket_tts_stream()` to `model.py`**
   - Resolves voice state, calls streaming generation
   - Converts float32 → int16 PCM bytes per chunk
   - Handles seed, voice_id, error conditions

3. **Modify `/v1/audio/speech` in `app.py`**
    - Pocket-TTS + `pcm` format → streaming handler (Flask Response with generator + `direct_passthrough=True`)
    - Other backends/formats or repair-enabled → existing batch behavior
    - No `stream` parameter needed — OpenAI spec streams by default

4. **Update Pocket-TTS runtime to expose streaming capability**
   - Optional: add a `streaming_available` flag to `/health` or `/status`

5. **Test with Hermes config**
   - Configure Hermes TTS: `tts.provider: openai`, `tts.openai.base_url: <our endpoint>`, `tts.openai.model: any`
   - Verify `with_streaming_response.create()` works end-to-end
   - Verify PCM format matches (int16, 24kHz, mono)

6. **Optional: Qwen3-TTS streaming for Hermes**
   - Reuse existing `/generate/stream` logic
   - Add path in `/v1/audio/speech` for OpenVINO backend streaming

## Risks and Open Questions

### 1. Gunicorn thread blocking during streaming
- The worker thread is occupied while streaming. With max_workers=4 threads in gthread, only one stream can run at a time (due to serialized executor for model access).
- Mitigation: This matches current `/generate/stream` behavior. Hermes voice mode is one conversation at a time.
- Open question: Should we add a queue for concurrent streaming requests?

### 2. Chunk size tuning for Pocket-TTS
- Pocket-TTS's `generate_audio_stream()` chunk sizes are opaque. If chunks are too large, TTFB increases; too small, overhead increases.
- Mitigation: Measure actual chunk sizes and TTFB. Optionally buffer and re-chunk in our generator.

### 3. Post-processing and prosody repair compatibility
- Batch generation applies `_trim_post_eos_tail()`, silence trimming, prosody repair, and full DSP (compression, EQ, LUFS, peak limit) via style presets.
- Streaming applies telepresence EQ (high-pass 80Hz + mild presence boost) per chunk, but skips: tail trim, silence trim, prosody repair, compression, LUFS normalization.
- Trade-off: Streaming = low latency, good quality. Batch = higher latency, highest quality.
- Opt-out: `postprocess=False` or `TTS_DEFAULT_DSP=off` disables batch DSP.

### 4. Hermes sentence-level chunking vs. our chunk format
- Hermes chunks LLM output by sentences and calls TTS once per sentence. Our streaming endpoint streams one utterance's worth.
- This is compatible: Hermes calls `/v1/audio/speech` with one sentence at a time, and our endpoint streams that sentence's audio.
- The `SentenceChunker` in Hermes decides sentence boundaries, not us.

### 5. Error handling in streaming
- If generation fails mid-stream, how do we signal the error? Options:
  - HTTP close with non-zero exit
  - Last chunk contains an error message
- Current Hermes `OpenAIStreamer` catches exceptions from `stream()` and logs; it handles mid-stream errors gracefully.

### 6. `stream_format` parameter support
- The OpenAI API now supports `stream_format: "sse" | "audio"`. Hermes doesn't currently use this.
- Decision: Support only raw audio streaming for now. Add SSE mode later if needed.

## Verification Commands

After implementation:

```bash
# Test streaming endpoint (Pocket-TTS + pcm streams by default)
curl -N -X POST http://localhost:8318/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello, this is a streaming test.", "model": "pocket-tts", "voice": "default", "response_format": "pcm"}' \
  | ffplay -nodisp -autoexit -ar 24000 -ac 1 -f s16le -

# Test batch endpoint still works (mp3/wav use batch)
curl -X POST http://localhost:8318/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello", "model": "pocket-tts", "voice": "default", "response_format": "wav"}' \
  -o test.wav && ffplay test.wav

# Verify wav format
python -c "
import wave
with open('test.wav', 'rb') as f:
    w = wave.open(f)
    print(f'channels={w.getnchannels()} rate={w.getframerate()} sampwidth={w.getsampwidth()}')
"

# Test with Hermes OpenAI SDK config:
# tts:
#   provider: openai
#   openai:
#     base_url: http://localhost:8318/
#     api_key: dummy
#     model: pocket-tts
#     voice: default
```

## References

- Hermes TTS streaming: https://github.com/NousResearch/hermes-agent/blob/main/tools/tts_streaming.py
- Hermes streaming docs: https://github.com/NousResearch/hermes-agent/blob/main/docs/streaming-tts.md
- OpenAI SDK speech.py: https://github.com/openai/openai-python/blob/main/src/openai/resources/audio/speech.py
- OpenAI SDK response handling: https://github.com/openai/openai-python/blob/main/src/openai/_response.py
- Pocket-TTS Python API: https://kyutai-labs.github.io/pocket-tts/API%20Reference/python-api/
- Existing codebase streaming: `src/qwen3_tts/app.py:2555`, `src/qwen3_tts/model.py:1944`, `src/qwen3_tts/streaming.py`
