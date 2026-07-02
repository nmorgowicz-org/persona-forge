# Investigation: PyTorch-backend (`TTS_BACKEND=pytorch`) main-talker attention shape bug

**Status:** open, unscoped, not yet fixed. Found as a side effect of validating a separate,
now-fixed OpenVINO bug (see `docs/dev/resolved/EXPORT_PIPELINE_INT4_NAN_FIX.md`) — nobody has
actually debugged this one yet, only reproduced the crash.

**Written:** 2026-07-02. Assume fresh context — this doc should be self-sufficient.

**Does this block anything?** No. The OpenVINO serving path (`TTS_BACKEND=openvino`, the
production/default backend — see `compose.yml`'s `TTS_BACKEND: ${TTS_BACKEND:-openvino}`) never
executes the eager PyTorch attention code this bug lives in. This only matters if something needs
the PyTorch backend to actually work (a "rollback gate" / fallback path, or a box without
OpenVINO). Do not treat this as blocking VoiceDesign UI work.

## Symptom

Every real `/generate` request against the PyTorch backend fails with:

```
{"error":"Inference error: mat1 and mat2 shapes cannot be multiplied (1x350208 and 2048x2048)"}
```

Full traceback (captured 2026-07-02, from `docker logs <container>`):

```
File ".../qwen_tts/core/models/modeling_qwen3_tts.py", line 1523, in forward
    layer_outputs = decoder_layer(
        hidden_states, ... **flash_attn_kwargs,
File ".../transformers/modeling_layers.py", line 93, in __call__
    super().__call__(*args, **kwargs)
File ".../torch/nn/modules/module.py", line 1789, in _call_impl
    return forward_call(*args, **kwargs)
File ".../qwen_tts/core/models/modeling_qwen3_tts.py", line 1392, in forward
    hidden_states, self_attn_weights = self.self_attn(
        hidden_states=hidden_states, ...
File ".../torch/nn/modules/module.py", line 1789, in _call_impl
    return forward_call(*args, **kwargs)
File ".../qwen_tts/core/models/modeling_qwen3_tts.py", line 805, in forward
    self.o_proj(attn_output)
File ".../torch/nn/modules/linear.py", line 134, in forward
    ... self.weight, self.bias
RuntimeError: mat1 and mat2 shapes cannot be multiplied (1x350208 and 2048x2048)
```

`350208 = 171 × 2048` — i.e. `171` is the prefill token count and `2048` is the hidden size for
this profile. That factorization is the single most important clue: `attn_output` reached
`o_proj` (a `nn.Linear(2048, 2048)`) as a flattened `(1, seq*hidden)` 2D tensor instead of the
expected `(1, seq, hidden)` 3D tensor.

This is **not new** — it was already flagged as a known, separate issue during the earlier
2026-07-01/07-02 NaN investigation (see "Ruled out" / "Confirmed separate, independent bug"
sections of the resolved doc), never actually investigated beyond reproducing the crash.

## Environment / exact reproduction

- **Box:** `dockermisc1` (`ssh dockermisc1`). Shared host — other people's containers live under
  `~/docker`; never touch containers you didn't start. See memory `dockermisc1-ops.md` and
  `dockermisc1-shared-host-caution.md`.
- **Repo location:** `~/projects/qwen3-tts-openvino-voicedesign-test` on dockermisc1 (a synced
  copy of this repo's `feat/voice-design` branch, container renamed to
  `qwen3-tts-voicedesign-test` to avoid colliding with the separate legacy `~/docker` deployment
  — do not touch that one).
- **Image:** `qwen3-tts-openvino:local`, built from that directory's `Dockerfile`.
- **`.env` in that directory:**
  ```
  REF_AUDIO_PATH=/var/data/autopirate/hermes-gateway/scratch/tts_samples/voice_A.wav
  REF_TEXT=Welcome to Rosies. What can I get for you today? You know, Im a good girl. You want me, dont you? I am on the menu too.
  MODEL_SIZE=1.7B
  QWEN3_TTS_PORT=8319
  ```
- **Versions in the image:** `transformers==5.12.1`, `torch==2.12.1+cpu`, `qwen_tts` installed at
  `/usr/local/lib/python3.13/site-packages/qwen_tts/`. `flash-attn` is not installed, so this
  path always runs the eager attention implementation — `self.config._attn_implementation` is
  presumably `"eager"`, meaning `attention_interface = eager_attention_forward` at
  `modeling_qwen3_tts.py:788` (see below).

**Repro command:**

```bash
ssh dockermisc1
cd ~/projects/qwen3-tts-openvino-voicedesign-test
TTS_BACKEND=pytorch docker compose up -d qwen3-tts
# wait ~10-20s for "Model loaded and ready" in: docker logs qwen3-tts-voicedesign-test
curl -sS -m 90 -X POST http://localhost:8319/generate -H 'Content-Type: application/json' \
  -d '{"text":"Hello there.","language":"English"}'
# -> 500 {"error":"Inference error: mat1 and mat2 shapes cannot be multiplied (1x350208 and 2048x2048)"}
```

100% reproducible on a normal short-text request — this is not an edge case or a long-sequence-only
failure as far as has been confirmed (earlier notes speculated "long sequences/prefill" but that
was never actually pinned down against a short-sequence control; the repro above uses a
completely ordinary short prompt, exactly like the one that works fine on the OpenVINO backend).

**Resource note:** this backend loads the full FP32 PyTorch model (no OpenVINO IR, no weight
release). On 2026-07-02 the host was seen down to ~270MB free RAM with 8.6/15GB swap in use while
this container sat idle after the crash — the host is memory-constrained in general (other
services on the box). Stop this container (`docker compose stop qwen3-tts`) as soon as you're
done testing; don't leave it running unattended.

## Relevant code (from the installed `qwen_tts` package, not this repo)

File: `/usr/local/lib/python3.13/site-packages/qwen_tts/core/models/modeling_qwen3_tts.py`
(installed into the image via pip; this repo patches a few lines of it via `Dockerfile`
string-replace for unrelated transformers-5.x fixes — see the `Dockerfile`'s
`python -c "..."` block — but nothing there touches this code path).

**`Qwen3TTSTalkerAttention.forward`, ~line 774-807** (the eager `self_attn` called from the
decoder layer):

```python
input_shape = hidden_states.shape[:-1]
hidden_shape = (*input_shape, -1, self.head_dim)
query_states = self.q_norm(self.q_proj(hidden_states).view(hidden_shape)).transpose(1, 2)
key_states = self.k_norm(self.k_proj(hidden_states).view(hidden_shape)).transpose(1, 2)
value_states = self.v_proj(hidden_states).view(hidden_shape).transpose(1, 2)
cos, sin = position_embeddings
query_states, key_states = apply_multimodal_rotary_pos_emb(
    query_states, key_states, cos, sin,
    self.rope_scaling["mrope_section"], self.rope_scaling["interleaved"]
)
if past_key_values is not None:
    cache_kwargs = {"sin": sin, "cos": cos, "cache_position": cache_position}
    key_states, value_states = past_key_values.update(key_states, value_states, self.layer_idx, cache_kwargs)
attention_interface: Callable = eager_attention_forward
if self.config._attn_implementation != "eager":
    attention_interface = ALL_ATTENTION_FUNCTIONS[self.config._attn_implementation]
attn_output, attn_weights = attention_interface(
    self, query_states, key_states, value_states, attention_mask,
    dropout=0.0 if not self.training else self.attention_dropout,
    scaling=self.scaling, sliding_window=self.sliding_window,
)
attn_output = attn_output.reshape(*input_shape, -1).contiguous()
return self.o_proj(attn_output)  # <-- line 805, crash site
```

Note `input_shape = hidden_states.shape[:-1]` is computed **once, at the very top**, from
whatever `hidden_states` looks like when this function is entered. The final
`attn_output.reshape(*input_shape, -1)` will always succeed (reshape doesn't fail just because
the shape is "wrong" — it fails only on element-count mismatch) and will silently produce a 2D
`(1, 350208)` tensor if `input_shape` was `(1,)` instead of `(1, 171)`. **This means the bug is
not really in this function** — `self_attn` is just where the wrongly-shaped tensor finally hits
a shape-sensitive op (`nn.Linear`). The real question is why `hidden_states` was already 2D
(`(1, 350208)`) rather than 3D (`(1, 171, 2048)`) by the time it reached `self_attn`.

**Caller chain above this** (`Qwen3TTSTalkerDecoderLayer.forward`, ~line 1392, and
`Qwen3TTSTalkerModel.forward`, ~line 1490-1533): both look structurally ordinary — the decoder
layer calls `self.self_attn(hidden_states=hidden_states, ...)` directly, and the model's decoder
loop just threads `hidden_states = layer_outputs[0]` through each layer. Nothing there reshapes
`hidden_states`. So if `hidden_states` enters the model already 2D, or becomes 2D on layer 0's
output, that's the actual bug site — not yet determined which.

**Input construction** (`Qwen3TTSModel`'s top-level generation path, ~line 2225-2261, building
what eventually becomes `inputs_embeds` passed to `self.talker.generate(...)`): inspected this
session and it looks structurally correct — per-sequence embeds are built as `(1, seq_i, hidden)`
3D tensors, `.squeeze(0)`'d to `(seq_i, hidden)` 2D, then `torch.nn.utils.rnn.pad_sequence(...,
batch_first=True)` re-batches them back into a proper `(batch, max_len, hidden)` 3D tensor before
`self.talker.generate(inputs_embeds=talker_input_embeds, ...)` is called. This construction was
**not** ruled out with certainty (no shape assertion was added and re-run), but it does not look
like the obvious culprit.

**No custom `prepare_inputs_for_generation`**: `Qwen3TTSTalkerForConditionalGeneration` (class at
line 1554, the main talker's own top-level `GenerationMixin` subclass) does not override
`prepare_inputs_for_generation`. It relies entirely on the base `GenerationMixin`'s default
implementation from `transformers==5.12.1`. This is a first-step, `inputs_embeds`-only generation
call (no `input_ids` passed in) — a less common, less battle-tested code path in
`GenerationMixin`, and `transformers==5.12.1` is a very new release. This is the most promising
unexplored lead: HF's default `prepare_inputs_for_generation` / `_prepare_model_inputs` /
`_expand_inputs_for_generation` logic for embeds-only first-step calls, on this specific
transformers version, is a plausible place for a silent flatten to sneak in — and would explain
why nothing in `qwen_tts`'s own code (which has zero `.view(-1` / `.reshape(-1` / `.flatten(`
calls anywhere in this file, confirmed by grep) is doing it.

## What's confirmed vs. not

**Confirmed:**
- 100% reproducible crash, exact error string and shapes as above.
- `qwen_tts`'s own `modeling_qwen3_tts.py` contains no `.view(-1...)`, `.reshape(-1...)`, or
  `.flatten(...)` calls anywhere (grepped the whole file) — so if hidden_states gets flattened,
  it's not an explicit call in this file.
- The numbers `1×350208` factor exactly as `171 (seq) × 2048 (hidden)` for this prompt/profile.
- Unrelated to the RoPE/INT4-NaN bug fixed the same day (`transformers_compat.py`'s
  `repair_rotary_buffers()`) — that fix is loaded and applied in this same PyTorch-backend
  container (visible in its startup log: `Repaired and validated RoPE buffers: [...]`), and the
  crash still happens. The OpenVINO backend, using the same fixed checkpoint loader, works fine.

**Not confirmed / open questions:**
- Exactly which call/frame first produces a 2D `hidden_states`/`inputs_embeds` — no shape-print
  instrumentation has been added yet at the model or `self_attn` entry points for this specific
  bug (a `diag_talker.py`-style monkeypatch, as used for the earlier RoPE investigation, would
  work well here — see "Suggested next steps").
- Whether this is really a `transformers==5.12.1` API/behavior change (in `GenerationMixin`
  internals) or a `qwen_tts`-package-only bug exposed by that transformers version.
- Whether it also affects `Qwen3TTSTalkerCodePredictorModelForConditionalGeneration` (the
  code_predictor's own separate `GenerationMixin` subclass, class at line 1154) or is main-talker
  specific.
- Whether sequence length matters at all (short prompt already reproduces it, per the repro above
  — so the earlier "long sequences" framing from prior sessions looks wrong, but this hasn't been
  cross-checked against, e.g., a single-token prefill).

## Suggested next steps

1. **Shape-print instrumentation, cheapest first step.** Monkeypatch
   `Qwen3TTSTalkerForConditionalGeneration.forward` (or `.generate`) and
   `Qwen3TTSTalkerAttention.forward` at the class level (use `functools.wraps` on the patched
   function — a bare `def patched_forward(self, *a, **kw)` without it breaks
   `transformers`' `_validate_model_kwargs`, which inspects `inspect.signature(model.forward)`;
   this bit a previous diagnostic session, see `docs/dev/resolved/EXPORT_PIPELINE_INT4_NAN_FIX.md`'s
   source history). Print `hidden_states.shape` / `inputs_embeds.shape` on every call. Run via
   `docker run --entrypoint python3 qwen3-tts-openvino:local /app/<script>.py` against
   `TTS_BACKEND=pytorch`, same pattern as the RoPE investigation's `diag_talker.py`. This will show
   directly whether `hidden_states` is already 2D at layer 0's entry (bug is upstream of the
   decoder loop, e.g. in `.generate()`'s internal input prep) or becomes 2D partway through (bug is
   inside a specific layer/module).
2. **Check `GenerationMixin`'s default `prepare_inputs_for_generation` / `_prepare_model_inputs`**
   in the installed `transformers==5.12.1` for embeds-only, no-input_ids first-step generation —
   this is the most under-inspected lead (see "No custom `prepare_inputs_for_generation`" above).
   Compare against how it should behave for a proper 3D `inputs_embeds`.
3. **Isolate with a synthetic direct call**, bypassing `.generate()` entirely: construct a
   deterministic `(1, N, 2048)` `inputs_embeds` tensor directly and call
   `Qwen3TTSTalkerForConditionalGeneration.forward(...)` (not `.generate(...)`) to see if the
   flatten happens even without `GenerationMixin` in the loop — this would rule in/out
   `GenerationMixin` as the culprit in one test.
4. **Check for a version pin mismatch**: confirm whether an older/pinned `transformers` version
   (e.g. whatever the pre-transformers-5.x working baseline used) exhibits the same bug against
   the same `qwen_tts` code, to determine if this is transformers-side API drift (same family as
   the three already-fixed export-pipeline bugs) or `qwen_tts`-side.

## Standing rules (repo conventions, apply here too)

- Only one heavy model-loading container/process at a time on dockermisc1.
- Never touch other `~/docker` containers on dockermisc1 without being asked.
- Never commit or push without explicit user ask.
- Prefer `run_in_background: true` (or equivalent) over long-running raw `nohup ssh ... &` for
  long diagnostics.
- Stop the PyTorch-backend test container when done — it's memory-heavy and the host is
  resource-constrained.
