# HANDOFF — unified container image follow-up

> Current work is on `fix/workflows-single-image`, based on released `v0.15.0` main. Follow
> **§4 What's left** and obey **§6 Hard rules**.

## 1. What this is

A small, OpenAI-compatible CPU TTS endpoint for the **hermes** agent: one container, one process, one
port `8318`, smallest footprint. One knob — `MODEL_SIZE` (`0.6B` or `1.7B`) — expands to a full
internal preset. OpenVINO IR is built once locally (`docker compose run --rm export`), not baked or
downloaded. Voice is **server-side** (mounted reference WAV); `/v1/audio/speech` `voice`/`ref_*`
fields are accepted but ignored.

```bash
cp .env.example .env              # edit REF_AUDIO_PATH, REF_TEXT, MODEL_SIZE
docker compose run --rm export    # one-time per MODEL_SIZE: writes /ov/<SIZE> IR
docker compose up                 # port 8318
curl -s localhost:8318/v1/audio/speech -H 'Content-Type: application/json' \
     -d '{"input":"hello there"}' -o out.mp3
```

## 2. Current state (branch `fix/workflows-single-image`, off released v0.15.0 `main`)

**The refactor is DONE and validated.** One merged Flask app (`qwen3_tts.app:app`), `src/` package
layout, `MODEL_SIZE` presets, one-command export, `serve.py`/port-8319 proxy removed, docs moved to
`docs/dev/`. Details are in git history and `docs/dev/OPENVINO_RESULTS.md`; do not re-do them.

Validated on `dockermisc1` (see OPENVINO_RESULTS.md for full provenance):
- **1.7B is the product-preferred profile** (user listening decision 2026-06-30; slightly better than
  0.6B and no memory disadvantage). Profile: main `int4_asym_g32` stateful cap768, predictor
  `int8_asym` explicit, **FP32 OpenVINO vocoder**, bf16 Torch glue.
- 0.6B profile: main+predictor INT8 stateful. Both pass MP3/WAV, missing-input OpenAI-400 envelope,
  and deterministic stream parity (`max_abs=0`, `SNR=inf`).
- **PyTorch rollback timeout: FIXED** (`config.py` no longer forces bf16 on the pytorch backend;
  that bf16-on-CPU GEMM was the >300 s regression). Verified 20.4 s on box.

## 3. Memory — RESOLVED

The "0.6B ≈ 1.7B memory" surprise is explained and the reduction work is done. Full analysis:
`docs/dev/OPENVINO_RESULTS.md`. The short version:

- Steady RSS is a **large fixed OpenVINO floor** (FP32 vocoder + runtime ≈ 2.7 GiB) plus a tiny
  (~0.3 GiB) variable IR/embedding delta. So **0.6B is not meaningfully smaller than 1.7B** → ship 1.7B.
- Normal single-utterance traffic peaks at **~5.4–5.8 GiB**, safe under the 10G limit. (The old
  "9.84 GiB" was a long-prompt/cold worst case that scales with KV occupancy toward cap768.)
- **Codec release SHIPPED** (`OPENVINO_RELEASE_CODEC`, default on): frees the ~0.32 GiB PyTorch
  `speech_tokenizer` after startup → **−381 MiB load, −466 MiB gen peak** on 1.7B. Fail-closed (no
  PyTorch decode fallback once freed); set `0` to keep the encoder for future per-request cloning.
- **INT8 vocoder: rejected with data** (net RSS *loss* — OpenVINO dequantizes to FP32 at inference).
  Do not re-attempt. The only untried memory levers left are small + parity-gated:
  `KV_CACHE_PRECISION=u8` and capacity 768→512.

## 4. What's left (do in this order)

1. **Single-image implementation is complete locally.** Docker now installs serving and export
   dependencies in one final image. Compose uses that image for both services and only overrides
   the export command. CI builds, caches, publishes, and smoke-tests one immutable SHA tag. Cleanup,
   operator docs, the M4 harness, repository validation, and the issue template use the same naming.

2. **Local model-free gates pass:** `scripts/validate_repo.py`, Compose config, shell syntax, JSON
   validation, and `git diff --check`. A local image build could not run because this Mac's Docker
   daemon is not available. After publishing the branch, apply `ready-to-test`; the
   `arc-general-docker` build/import smoke test is the remaining required gate.

3. **After CI passes, deploy an immutable image on `dockermisc1`.** Set `QWEN3_TTS_IMAGE` to
   `ghcr.io/nmorgowicz-org/qwen3-tts-openvino:<git-sha>`, run the Compose export profile only when IR
   must be regenerated, then start the service. Confirm `/health`, one short generation, and the
   startup `released ~0.32 GiB of PyTorch codec` log. Roll back by restoring the prior image digest.

4. **Optional follow-ups (not blockers):**
   - Re-measure codec release on **0.6B** (the A/B above was 1.7B-only) for symmetry.
   - Try the two remaining memory levers (`KV_CACHE_PRECISION=u8`, cap512) if long-paragraph traffic
     ever needs a lower peak — parity-gate each.
   - Alexandria features (per-request VoiceDesign/cloning) will need `OPENVINO_RELEASE_CODEC=0`
     because they revive the codec encoder. See `docs/plans/alexandria_ideas.md`.

## 5. dockermisc1 quick reference

Paths (host):
- IR (mounted to `/ov`): `/var/data/autopirate/qwen3-tts/openvino-simplify-v2/{0.6B,1.7B}`
- Model cache: `/var/data/autopirate/qwen3-tts/model` → `/root/.cache/huggingface/hub`
- Reference voice: `/var/data/autopirate/qwen3-tts/voice/voice_A.wav` → `/voice/reference.wav`
- Staged source worktree: `/tmp/qv2val`
- Images: runtime `qwen3-tts-openvino:simplify-v2-runtime`, exporter `…:simplify-v2-exporter`

Run a container (production recipe; add `-v /tmp/qv2val/src/qwen3_tts:/app/src/qwen3_tts:ro` only for
fast bind-mount iteration):
```bash
docker run -d --name qwen3-tts -p 8318:8318 --memory 10g --memory-swap 11g \
  -e TTS_BACKEND=openvino -e MODEL_SIZE=1.7B -e MODEL_REVISION= \
  -e REF_TEXT="Welcome to Rosies. What can I get for you today? ..." \
  -v /var/data/autopirate/qwen3-tts/model:/root/.cache/huggingface/hub:rw \
  -v /var/data/autopirate/qwen3-tts/openvino-simplify-v2:/ov:rw \
  -v /var/data/autopirate/qwen3-tts/voice/voice_A.wav:/voice/reference.wav:ro \
  qwen3-tts-openvino:simplify-v2
curl -sf localhost:8318/health
```

Measure memory (one fresh container per config; peak resets on recreate):
```bash
docker exec qwen3-tts cat /sys/fs/cgroup/memory.current   # idle load RSS
# ...POST /generate...
docker exec qwen3-tts cat /sys/fs/cgroup/memory.peak       # gen peak
```
NNCF and the export/parity tools are included in the same image as the serving runtime.

## 6. Hard rules (keep in effect)

- Never blanket `docker kill/stop/prune`; only touch `qwen3-tts*` containers. Leave `litellm*`,
  `litellm-postgres`, `headroom-proxy`, `crowdsec`, `hermes-*`, `*arr`, `searxng` running.
- Never run two large model jobs at once on the 15 GiB box; never two `--memory 13g` at once (OOM).
- Worker gunicorn: `-w 1`, **never** `--preload` (wastes ~2.8 GiB).
- Do NOT change `load_model`'s exporter fp32 dtype; `OPENVINO_TORCH_DTYPE` must stay UNSET for the
  exporter. Serving uses bf16 via the OpenVINO-only preset policy.
- Keep the `TTS_BACKEND=pytorch` rollback working (do not re-add forced bf16 on that path).

---
*History: the full step-by-step refactor plan (§1–§10 of the old handoff), the streaming-validation
handoff, and all milestone results are preserved in git history and `docs/dev/OPENVINO_RESULTS.md`.*
