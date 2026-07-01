# Handoff: transformers 5.x "free-run / never-stop" TTS bug

**Date:** 2026-07-01  **Branch:** `fix/t5-talker-eos-conditioning`  **Box:** `dockermisc1`

This document is written to be read by someone (or a smaller model) with **no prior context**.
Read it top to bottom. It tells you exactly what is broken, what has been proven, and the single
next experiment to run.

---

## 1. TL;DR (read this first)

- We upgraded `transformers` from **4.57.3** (worked) to **5.12.1** (broken) for CVE-2026-1839.
- Since then, the TTS model **never stops generating**. For input "Hi there." it produces ~17.5s of
  **fluent but WRONG English** (hallucinated: "…the whole town of San Juan" on a loop) instead of a
  1-second "Hi there.", and it never emits the end-of-speech token, so it runs until it hits the
  audio buffer capacity (768 frames) and crashes with `stateful cache capacity exceeded`.
- **This is NOT a drone, NOT broken audio, NOT RoPE, NOT the OpenVINO (OV) model.** The audio is
  perfectly natural speech — the model just **ignores the target text** and free-runs.
- **ROOT CAUSE — PROVEN:** the `inputs_embeds` tensor (the "prompt" that conditions the model,
  built by qwen_tts's PyTorch code) is **numerically different** under transformers 5.x than under
  4.57.3. We dumped this tensor from a known-good T4 run and the broken T5 run, for the *same input*,
  feeding the *same OV model*: the position IDs and attention mask are byte-for-byte identical, but
  **`inputs_embeds` differs at every one of the 170 prefill positions** (mean-abs-diff 0.085, max 16.9,
  std 0.078 vs 0.109). Same model + wrong prompt = wrong (free-running) output.
- **THE NEXT STEP** (Section 6): find *which part* of the `inputs_embeds` construction changed. The
  tensor is `text_embeds + reference_audio_codec_embeds` summed together. Dump the reference codes
  (`voice_clone_prompt.ref_code`) and the text embeds separately under T4 vs T5 to see which one moved.
  Strong suspects: (a) the reference-audio encoder `speech_tokenizer.encode` (its 12Hz tokenizer had a
  `@check_model_inputs` decorator stripped by a Dockerfile patch), or (b) an embedding/projection
  module behaving differently under transformers 5.x.

---

## 2. What the model is supposed to do vs what it does

- **Input:** text "Hi there." + a voice-clone reference (audio `voice_A.wav` whose transcript is
  `REF_TEXT="Welcome to Rosie's..."`). The model should say "Hi there." **in the reference voice**,
  then emit the codec end-of-speech token (id **2150**) and stop (~1 second of audio).
- **T4 (transformers 4.57.3), CONFIRMED GOOD:** says **"Hi there."**, 1.10 s, emits EOS, stops.
- **T5 (transformers 5.12.1), BROKEN:** says fluent hallucinated English ("…whole town of San Juan"
  looped 30+ times), never emits EOS, runs to the 768-frame cap and 500-errors.

To "hear" the audio we used OpenAI Whisper (`pip install openai-whisper`, model `small`) to transcribe
the WAV. That is how we discovered it is *fluent but wrong* rather than noise.

---

## 3. Architecture crash-course (so the terms below make sense)

- `Qwen3TTSForConditionalGeneration.generate()` (in the installed pip package
  `qwen_tts/core/models/modeling_qwen3_tts.py`) builds a big **prefill `inputs_embeds`** tensor from
  the text + the reference-audio codec codes, then calls `self.talker.generate()`.
- `self.talker` = `Qwen3TTSTalkerForConditionalGeneration`. Its `.generate()` is a standard
  HuggingFace `GenerationMixin` loop. Each step calls `self.talker.model.forward(...)` (the
  transformer stack) and a sub-model `self.talker.code_predictor` (predicts 15 extra codec codebooks
  per step).
- **Our serving code replaces `self.talker.model.forward` and `self.talker.code_predictor.model.forward`
  with OpenVINO (OV) inference** — see `src/qwen3_tts/openvino/talker.py`, class `_OVStatefulCore`,
  method `run()`, and the `install()` method which does the monkey-patching. So the transformer math
  runs as a pre-compiled OV graph; the surrounding Python (building `inputs_embeds`, sampling, the
  generation loop) still runs in PyTorch/transformers.
- **Important:** the OV model file was exported on **2026-06-29, BEFORE the T5 upgrade**, so the OV
  graph's weights and RoPE are "T4-baked" and correct. The user confirmed nothing was re-exported
  under T5. This is why we can feed the *same* OV graph two different `inputs_embeds` and see it work
  (T4) vs free-run (T5).
- The model stops ONLY when it *samples* codec token id **2150** (EOS). A diagnostic (see below)
  shows the probability of token 2150 stays pinned at ~0.000001 for the entire T5 run — the model
  never wants to stop, because its conditioning is wrong.

---

## 4. ROOT CAUSE — proven by a direct tensor diff

We ran the **same** request ("Hi there.") against two containers using the **same** OV model files,
same voice reference, same env — differing only in transformers version + code version:

- T4 reference: image `ghcr.io/nmorgowicz-org/qwen3-tts-openvino:v0.15.1` (transformers 4.57.3). WORKS.
- T5 broken:    image `qwen3-tts-test-b8901c9` (transformers 5.12.1). BROKEN.

In BOTH we dumped the tensors that go INTO the OV transformer at the prefill step (a temporary
`main_forward` hook that does `numpy.save("/tmp/dump_*_prefill.npy", ...)` when `/tmp/tts_dump`
exists). Comparison of the prefill inputs:

| tensor            | shape        | T4 vs T5 result |
|-------------------|--------------|-----------------|
| `position_ids`    | (3,1,170)    | **byte-identical** |
| `attention_mask`  | (1,170)      | **byte-identical** (all ones) |
| `cache_position`  | (170,)       | same after internal resolve |
| **`inputs_embeds`** | (1,170,2048) | **DIFFERENT: maxdiff 16.9, mean-abs-diff 0.085, T4 std 0.078 vs T5 std 0.109** |
| `out` (hidden)    | (1,170,2048) | different — but only *because* inputs_embeds differs |

Per-position analysis: **all 170 positions differ** (none identical). Early positions are much
smaller-norm under T5 (position 0: T4 norm 1.81 vs T5 0.37). Both models load at **bfloat16**, so
this is NOT a float32-vs-bfloat16 precision artifact — it is a real difference in how the
`inputs_embeds` is computed.

**Conclusion:** the OV model and all its other inputs are correct. The single thing that changed is
the **conditioning tensor `inputs_embeds`**, which is built by qwen_tts PyTorch code that behaves
differently under transformers 5.x. That is 100% why the model free-runs and never stops.

---

## 5. What has been RULED OUT (do not re-investigate these)

- **Tokenization / chat template:** correct under T5. "Hi there." → 11 tokens with
  `<|im_start|>assistant\n` ... `<|im_end|>\n<|im_start|>assistant\n`; special tokens are single ids
  (151644/151645); the hardcoded slice offsets `[:, :3]`, `[:, 3:4]`, `[:, 4:-5]`, `[:, -5:]` all
  land correctly.
- **Position IDs / mRoPE:** identical T4 vs T5 (proven by the dump). The OV decode override
  `position_ids = cache_position.unsqueeze(0)` produces the correct `[[prior]]`.
- **Attention mask:** identical.
- **generation_step / trailing_text_hidden threading:** advances correctly; `tth_len=1` is EXPECTED
  here (ICL streaming path bakes short text into the prefill, so trailing is just a pad).
- **KV cache / statefulness:** works — decode inputs and outputs both vary each step.
- **code_predictor structure:** runs its 15 sub-steps per talker step and resets correctly.
- **Model load dtype:** both bfloat16.
- **Text-delivery mode:** fails in BOTH `non_streaming_mode=False` (streaming) and `True`.
- **The OV model / exporter:** proven good — T4 works with the exact same OV files.

---

## 6. THE NEXT STEP (do this next)

The prefill `inputs_embeds` = **text embeddings + reference-audio codec embeddings**, summed and
concatenated inside `Qwen3TTSForConditionalGeneration.generate()` and its helper
`generate_icl_prompt()` (in `qwen_tts/core/models/modeling_qwen3_tts.py`, around lines 2010-2280 and
1956-2007). All 170 positions differ, so localize *which addend* moved:

1. **Dump `voice_clone_prompt.ref_code` under T4 and T5 and compare.** This is the reference-audio
   encoding, produced ONCE at startup by `model.create_voice_clone_prompt(...)` which calls
   `model.speech_tokenizer.encode(ref_wav)`. If `ref_code` differs, the **reference-audio encoder is
   the culprit**. Prime suspect: the Dockerfile patch that runs
   `sed -i '/@check_model_inputs/d' .../tokenizer_12hz/modeling_qwen3_tts_tokenizer_v2.py`
   (removes a transformers-5 decorator from the 12Hz codec model that encodes the reference). Removing
   that decorator may change what the encoder returns.
   - In `src/qwen3_tts/model.py`, after `voice_clone_prompt = model.create_voice_clone_prompt(...)`,
     add `import numpy as np; np.save('/tmp/refcode.npy', voice_clone_prompt[...].ref_code.cpu().numpy())`
     (inspect the structure — it is a list of items or a dict with key `ref_code`). Run under T4 (v0.15.1
     container) and T5 (b8901c9 container) and diff the two `.npy` files.

2. **If `ref_code` is identical**, then the difference is in the **text/codec embedding modules**
   (`talker.text_projection`, `talker.get_text_embeddings()`, `talker.get_input_embeddings()`,
   `code_predictor.get_input_embeddings()`). Dump the individual embedding outputs for a fixed input id
   under both versions and find which module diverges. Look at the Dockerfile patches (Section 7) —
   one of them may change an embedding path, or transformers 5.x may have changed `nn.Embedding` /
   projection behavior for this model config.

3. Once the diverging component is found, fix it (correct the patch, or adapt to the transformers-5.x
   API) so that `inputs_embeds` matches the T4 values. Verify by re-running the tensor dump: the
   prefill `inputs_embeds` should become byte-close to the T4 dump, and "Hi there." should transcribe
   correctly and emit EOS.

**The success criterion is objective:** transcribe the output WAV with Whisper — it must say
"Hi there." and be ~1 second (small file, e.g. ~5-9 KB mp3), and the request must return HTTP 200
without `stateful cache capacity exceeded`.

---

## 7. The transformers-5.x compat patches (candidates for the bug)

These are applied to the installed pip packages by the **Dockerfile** (repo root), lines ~27-51.
They only exist to make transformers 5.x import/run. One of them likely changed model numerics:

- `sed '/@check_model_inputs/d'` on `tokenizer_12hz/modeling_qwen3_tts_tokenizer_v2.py` — **top suspect**
  (this is the reference-audio encoder).
- In `modeling_qwen3_tts.py`: `self.padding_idx = getattr(config,"pad_token_id",None)`;
  `input_embeds=inputs_embeds` → `inputs_embeds=inputs_embeds`; removed a
  `cache_position=cache_position,` line (from `create_causal_mask`, which is deprecated/unused in T5 —
  benign for OV since the inner forward is replaced).
- In `configuration_qwen3_tts.py`: dropped `layer_type_validation` import / call.
- In `transformers/modeling_rope_utils.py`: re-added a custom `_compute_default_rope_parameters`
  (transformers 5.x removed the "default" rope type). **Note:** this only affects the PyTorch RoPE
  path; the OV graph has RoPE baked from the T4 export, so it does NOT affect the OV serving path — but
  it WOULD affect a pure-PyTorch backend run.

To compare a patch's effect: the T4 reference container (v0.15.1) has the **unpatched** qwen_tts and
the original transformers files — diff them against the patched T5 files.

---

## 8. How to reproduce & the diagnostics that exist

All diagnostics live in `src/qwen3_tts/openvino/talker.py` (in `install()`) and `src/qwen3_tts/model.py`
(`_run_generate`), on branch `fix/t5-talker-eos-conditioning`. They are **gated by flag files** so they
are off by default; turn on by `docker exec <container> sh -c "touch /tmp/<flag>"`:

- `/tmp/tts_step_diag` → `[step_diag]` (generation_step, trailing_text length), `[embed_diag]`
  (prefill inputs_embeds stats), `[main_diag]` (per-decode input/output norms), `[pred_diag]`
  (code_predictor sub-steps).
- `/tmp/tts_dump` → saves `/tmp/dump_*_prefill.npy` (the tensor dump used for the root-cause diff).
- `/tmp/tts_max_new` containing e.g. `220`, or env `TTS_MAX_NEW_TOKENS=220` → caps generation so it
  returns partial audio instead of crashing at capacity (useful to get a WAV to transcribe).
- `/tmp/tts_non_streaming` or env `TTS_NON_STREAMING=1` → forces `non_streaming_mode=True`.
- `[logits_diag]` (codec_head EOS probability per step) is always on when `TTS_LOGITS_DIAG=1` env is set
  (it is set in the running container). This is what shows EOS prob pinned at ~0.

**Deploy a code change without rebuilding the image** (keeps the OV model warm-ish; full reload is
only ~1.5-3 min from the on-disk OV cache):
```
scp src/qwen3_tts/openvino/talker.py dockermisc1:/tmp/talker.py
ssh dockermisc1 'docker cp /tmp/talker.py qwen3-tts:/app/src/qwen3_tts/openvino/talker.py && \
                 docker exec qwen3-tts sh -c "kill -HUP 1"'   # SIGHUP gunicorn master -> new worker imports new file
# then wait for "Model loaded and ready" in: docker logs qwen3-tts
```

**Fire a request (port 8318 is internal-only, so curl from inside the container):**
```
docker exec qwen3-tts sh -c 'curl -sS -m 240 -X POST http://127.0.0.1:8318/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"qwen3-tts\",\"input\":\"Hi there.\",\"voice\":\"default\"}" \
  -o /tmp/out.wav -w "HTTP %{http_code} size=%{size_download}\n"'
docker cp qwen3-tts:/tmp/out.wav .   # then transcribe with whisper
```

---

## 9. Container / ops state and constraints

- **Two containers exist for this work; they CANNOT run at the same time** (the box is 15 GiB RAM and
  each model needs ~5-9 GiB — running both will OOM and could kill other services). Stop one before
  starting the other.
  - `qwen3-tts`  = the T5 (broken) service, image `qwen3-tts-test-b8901c9`. **Currently RUNNING** with
    the temporary tensor-dump `talker.py` docker-cp'd in (not in the image).
  - `qwen3-tts-t4ref` = the T4 (good) reference, image `...:v0.15.1`. **Currently STOPPED.** Start with
    `docker start qwen3-tts-t4ref` (stop `qwen3-tts` first). Its env came from `/tmp/t4ref.env` on the box.
- **Restore the real service cleanly** (fresh from image, discards docker-cp'd diagnostics):
  `cd /home/nick/docker && docker compose up -d --force-recreate --no-deps qwen3-tts`
  (if a name conflict: `docker rm -f qwen3-tts` first).
- **Do NOT** run two large model jobs at once; **only** touch `qwen3-tts*` containers; leave
  `litellm*`, `headroom-proxy`, `hermes-*`, `*arr`, `searxng`, `crowdsec` running.
- The OV kernel cache is at `/var/data/autopirate/qwen3-tts/openvino/cache/`. First-ever compile is
  ~13 min; a worker restart reloads from disk in ~1.5-3 min. Do not delete it.
- hermes consumes the **batch** endpoint `/v1/audio/speech` (complete file), NOT streaming. So the fix
  must make the batch path work; streaming has no consumer.

## 10. Pragmatic fallback (if a proper fix is not reached)

The v0.15.1 image (transformers 4.57.x) **works today**. Rolling the live service back to it unblocks
hermes immediately; CVE-2026-1839 is the only reason for staying on transformers 5.x, and this is an
internal, trusted-network service (port 8318, no auth). The user's stated preference is to FIX T5, so
treat rollback as a last resort, not the goal.

## 11. Key files

- `src/qwen3_tts/openvino/talker.py` — OV serving runtime + all diagnostics (`_OVStatefulCore.run`,
  `install`, `main_forward`, `predictor_forward`, `_resolve_position_ids`, `_cache_position_or_default`).
- `src/qwen3_tts/model.py` — `_run_generate` (calls `generate_voice_clone`), diag flags, EOS logits proc.
- `Dockerfile` (root) — the transformers-5.x compat patches (Section 7).
- Installed package (inside container) `/usr/local/lib/python3.13/site-packages/qwen_tts/core/models/
  modeling_qwen3_tts.py` — `generate()` (~2010), `generate_icl_prompt()` (~1956) build `inputs_embeds`.
- Memory notes: `t5-freerun-not-drone.md`, `t5-input-ids-bug.md` (an earlier, partly-superseded theory).
