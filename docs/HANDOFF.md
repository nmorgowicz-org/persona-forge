# HANDOFF — simplify-v2 production refactor

> **Read this top to bottom before changing anything.** It is written to be followed by an
> automated assistant. Do the steps **in order**. Do not skip the validation step (§10). Do not
> invent file names or env vars that are not listed here.

## 0. Context (what and why)

We are simplifying this project so a non-expert can run a small OpenAI-compatible TTS endpoint for
the **hermes** agent, with the **smallest footprint**, and an **A/B of the 0.6B vs 1.7B** models.

- **Branch:** `refactor/simplify-v2` (already created, off `main`). `main` is the released, working
  **v0.14.0** baseline — DO NOT touch `main`.
- **Target user experience:**
  ```bash
  cp .env.example .env             # edit 3 lines: REF_AUDIO_PATH, REF_TEXT, MODEL_SIZE
  docker compose run --rm export   # one-time per model size: builds the OpenVINO IR locally
  docker compose up                # one container, one port 8318
  curl -s localhost:8318/v1/audio/speech \
       -H 'Content-Type: application/json' \
       -d '{"input":"hello there"}' -o out.mp3
  ```
  A/B test: set `MODEL_SIZE=1.7B` in `.env`, re-run export + up, compare.

## 1. The 5 approved decisions (do not relitigate)

1. **One container, one process, one port `8318`.** Merge the old `app_api.py` (proxy) and
   `app_worker.py` (model) into a **single Flask app** whose endpoints call the model **directly**
   (no internal HTTP proxy). **Delete `serve.py`**, the second gunicorn, port `8319`, and the proxy.
2. **`MODEL_SIZE` is the only model knob** (`0.6B` or `1.7B`). Everything else (`OPENVINO_*`, `OV_*`,
   IR paths, capacity, memory) becomes an internal **preset**, not a user-facing env var. Keep a
   `TTS_BACKEND=pytorch` zero-IR fallback for "just run it without exporting".
3. **OpenVINO IR delivery = one-command local export.** `docker compose run --rm export` runs the
   exporter and writes IR to a **local volume** at **stable, MODEL_SIZE-keyed paths** (no hashes).
   The IR is NOT baked into the image and NOT downloaded from anywhere.
4. **Full `src/` package layout.** `src/qwen3_tts/` is the service package. `src/export/` holds the
   maintainer/export tooling as flat modules on `PYTHONPATH` (they import each other by bare name;
   only their imports of the *shared* modules change to `qwen3_tts.*`).
5. **Docs:** fold every still-true operational fact from the OLD `HOW_TO_RUN.md` into the new
   methodology, THEN replace it. Write a new user+advanced `HOW_TO_RUN.md`. Move dev docs to
   `docs/dev/`. This HANDOFF is the continuity doc.

## 2. Target repository structure

```
qwen3-tts-openvino/
├─ README.md                 # short: what it is + 20-line quickstart + links
├─ .env.example              # REF_AUDIO_PATH, REF_TEXT, MODEL_SIZE (+ commented advanced)
├─ compose.yml               # ONE service (8318) + `export` profile, MODEL_SIZE-driven
├─ Dockerfile                # runtime + exporter stages; entrypoint = qwen3_tts.app:app
├─ requirements/             # runtime.txt, openvino.txt, export.txt
├─ src/qwen3_tts/            # the service package  (PYTHONPATH=/app/src)
│   ├─ __init__.py           # DONE
│   ├─ app.py                # TODO: merged Flask app (see §4)
│   ├─ model.py              # TODO: model load + generation (from app_worker.py, no Flask) (§5)
│   ├─ presets.py            # DONE — MODEL_SIZE -> settings (§6); validated locally
│   ├─ config.py             # DONE — apply_preset_env() sets low-level env (§6); validated locally
│   ├─ model_config.py       # DONE (moved) — HF token + repo + torch dtype helpers
│   ├─ streaming.py          # DONE (moved, was streaming_vocoder.py) — StreamingVocoderSession
│   └─ openvino/
│       ├─ __init__.py       # DONE
│       ├─ runtime_config.py # DONE (moved, was ov_runtime_config.py)
│       ├─ talker.py         # DONE (moved, was ov_talker_runtime.py; lazy imports fixed)
│       └─ vocoder.py        # DONE (moved, was ov_vocoder_runtime.py)
├─ src/export/               # TODO: move export tooling here (§7)
├─ scripts/                  # export.py (one-command export), ab_test.sh, download_model.py, transform_stateful_ir.py
├─ tests/                    # TODO: update imports to qwen3_tts.* (§8)
└─ docs/
    ├─ HANDOFF.md            # this file
    ├─ HOW_TO_RUN.md         # TODO: rewrite (§9)
    ├─ plans/
    └─ dev/                  # TODO: move OPENVINO_IMPLEMENTATION/RESULTS, PLAN_* here
```

## 3. Progress so far (state of the branch)

DONE:
- Branch `refactor/simplify-v2` created off `main`.
- `src/qwen3_tts/` + `src/qwen3_tts/openvino/` packages scaffolded with `__init__.py`.
- Moved via `git mv`: `ov_runtime_config.py → openvino/runtime_config.py`,
  `ov_talker_runtime.py → openvino/talker.py`, `ov_vocoder_runtime.py → openvino/vocoder.py`,
  `streaming_vocoder.py → streaming.py`, `model_config.py → qwen3_tts/model_config.py`.
- Fixed the two lazy bare-name imports inside `talker.py` to
  `from qwen3_tts.openvino.runtime_config import get_ov_config` and
  `from qwen3_tts.openvino.vocoder import OpenVinoVocoderRuntime`.
- Created empty dirs: `src/export/`, `requirements/`, `docs/dev/`.
- **Wrote `src/qwen3_tts/presets.py` and `src/qwen3_tts/config.py`** (§6) — validated locally
  (`PYTHONPATH=src python -c "from qwen3_tts import config; config.apply_preset_env(...)"`):
  case-insensitive MODEL_SIZE, stable IR paths, expert override wins, bad-size errors clearly.

TODO (in order): §4 app.py, §5 model.py, §7 export move, §8 Dockerfile/compose/env/tests,
§9 docs, §10 validate. (presets/config from §6 are DONE.)

### 2026-06-30 continuation checkpoint (`refactor/simplify-v2`)

The TODO line above describes the state at handoff creation. Current branch state is now:

- §4 and §5 implemented: `src/qwen3_tts/app.py` is the one-process API; model loading and
  generation live in `model.py`. There is no internal HTTP proxy or port 8319.
- The validated model profiles are explicit: 0.6B uses INT8 stateful main cap768 plus INT8
  stateful predictor cap32; 1.7B uses INT4 asymmetric group-32 stateful main cap768 plus INT8
  explicit predictor. Both use the FP32 OpenVINO vocoder and BF16 Torch glue.
- §7 modules moved to `src/export`; shared imports and exporter source hashing were updated.
- `scripts/export.py` assembles stable `/ov/<SIZE>` paths. For 1.7B it performs separate INT8 and
  INT4 exports so only the main core comes from INT4; it then transforms the stateful main. For
  0.6B it additionally transforms the predictor at cap32. This orchestration is syntax-checked but
  has **not yet run a full model export**.
- §8 wiring implemented: one-port Dockerfile, `compose.yml`, split `requirements/`, `.env.example`,
  package-aware CI/test imports, direct-model API tests, and obsolete `serve.py`/serve test removed.
- §9 implemented at the operational level: concise README, rewritten HOW_TO_RUN, and developer
  plans/results moved to `docs/dev`. Additional stale internal links should be checked before PR.
- Local results: `scripts/validate_repo.py` passes; all `src/`, `scripts/`, and selected test Python
  files compile; Compose config passes when `REF_AUDIO_PATH` and `REF_TEXT` are supplied;
  `git diff --check` passes. The Mac host lacks Flask/Numpy/SoundFile, but all 53 model-free tests
  passed inside the runtime image on `dockermisc1`.
- Target result: both images built, exporter imports passed, and the fresh 0.6B export plus HTTP
  smoke gates passed. Runtime health reports stateful INT8 main cap768, stateful INT8 predictor
  cap32, and FP32 OpenVINO vocoder. Post-request container memory was 5.907 GiB. Exact provenance,
  output paths, and remaining gates are recorded in `docs/dev/OPENVINO_RESULTS.md`.
- Follow-up: deterministic 0.6B stream parity passed exactly (`max_abs=0`, `SNR=inf`); five warm
  production-sampling requests had 19.43-second median latency and approximately 5.94 median RTF.
  PyTorch backend startup passed, but actual rollback generation timed out at 300 seconds and
  returned no audio. OpenVINO was restored. Treat rollback generation as a blocking failed gate.

Next steps, in order:

1. Diagnose the PyTorch rollback timeout without weakening the 300-second public API contract.
2. Complete 0.6B listening and the larger warm benchmark sample required by the implementation plan.
3. Repeat export/start/generation for 1.7B. Verify health reports main `stateful-int4`, predictor
   `int8`, and OpenVINO vocoder enabled; if health reports FP32 main, stop and fix graph selection.
4. Run deterministic batch/stream parity, warm latency/RSS collection, and A/B listening. Record
   source commit, image ID/digest, model revision, metadata hash, host memory/swap, and saved audio
   paths in `docs/dev/OPENVINO_RESULTS.md`.
5. Update this checkpoint with real results, then commit in logical chunks and open the PR with one
   Conventional Commit line per release-note item in the override block.

### 2026-06-30 final operator state after commit `377287e`

`377287e refactor(service): simplify runtime and local export` is pushed to
`origin/refactor/simplify-v2`. Host `gh auth status` succeeds when run outside the sandbox. No PR has
been opened yet. The documentation changes in this final operator section are the only post-commit
worktree changes and must be committed/pushed before handoff.

Current `dockermisc1` state:

- `qwen3-tts` is healthy and running the **1.7B OpenVINO** profile from local image
  `qwen3-tts-openvino:simplify-v2-runtime`
  (`sha256:c93d0267d73f5352fc8c6a3d5634ec3cbfde7fb6fc3976cdab6dabad2e759063`).
- Exporter image:
  `sha256:9607147cdf069adc17899d7245a8ff4179390822f67e8acb1736cbbb014de15c`.
- Validation checkout: `/tmp/qwen3-tts-simplify-v2`. It is a tar-staged worktree, not a Git
  checkout. The original `/home/nick/projects/qwen3-tts-openvino` checkout was not modified.
- Isolated artifacts: `/var/data/autopirate/qwen3-tts/openvino-simplify-v2/{0.6B,1.7B}`. Existing
  production artifacts under `/var/data/autopirate/qwen3-tts/openvino` were not modified.
- Model cache: `/var/data/autopirate/qwen3-tts/model`. Reference:
  `/var/data/autopirate/qwen3-tts/voice/voice_A.wav` with the Rosie transcript already recorded in
  the Compose invocation/history above.
- The previous `qwen3-tts-candidate` (`runtime-v0.13.0`) remains present but stopped.

1.7B validated configuration and provenance:

- Model revision `fd4b254389122332181a7c3db7f27e918eec64e3`; metadata source hash
  `a6f9dc107cc69a2b`.
- Main `int4_asym_g32`, stateful cap768. Stateful XML SHA-256
  `2ced2c3e91676efb77d44373fbe60906de37359a3d6a8746a14298e710c3ed1d`, 56 states shaped
  `[1,8,768,128]`, compile smoke passed.
- Predictor `int8_asym`, explicit cache. FP32 OpenVINO vocoder enabled. BF16 low-memory Torch glue.
- Health reports `active_main_compression=stateful-int4`,
  `active_predictor_compression=int8`, `stateful_predictor=false`, and vocoder enabled.
- MP3, native WAV, missing-input OpenAI envelope, and bounded deterministic streaming parity passed.
  Parity (`do_sample=false`, seed 1234, max 32) had max absolute error 0, infinite SNR, 26 generated
  frames, and 25.97-second total/TTFB.
- Five production-sampling WAVs took 21.16, 22.47, 22.50, 22.65, and 24.18 seconds. Median latency
  22.50 seconds; nearest-rank p95 24.18 seconds; audio duration 2.85-3.71 seconds; median RTF about
  7.39. Files: `/tmp/simplify-17-warm-{1..5}.wav` and `/tmp/simplify-17-warm.tsv`.
- Listening/A-B quality evaluation is still required. Do not infer quality from tensor parity.

#### Memory accounting and reduction work

Do not collapse the following into one number:

- Immediately after the first 1.7B generations, Docker working-set reporting was 9.686 GiB / 10
  GiB and cgroup peak was 10,561,286,144 bytes (9.84 GiB). This leaves almost no cgroup peak margin.
- Process `VmRSS`/`VmHWM` was about 7.62 GiB, consistent with the earlier cap768 measurements.
- After five warm requests, Docker reported 5.448 GiB / 10 GiB because 4.69 GB of cgroup file pages
  became `inactive_file` and Docker subtracts reclaimable inactive file cache. At that point cgroup
  `anon` was 5.79 GB, total `file` 4.71 GB, `inactive_file` 4.69 GB, and process `VmRSS` 7,991,484
  kB. The cgroup peak remained 9.84 GiB.
- Therefore the apparent 9.69 -> 5.45 GiB drop is mainly active-to-inactive file-cache accounting,
  not model tensors being freed. Use `memory.current`, `memory.peak`, `memory.stat`, process
  `VmRSS/VmHWM`, host available RAM, and swap together. Reset peak by recreating the container.

Ranked memory-reduction hypotheses:

1. **Release the unused PyTorch speech-tokenizer model after prompt creation and successful OV
   vocoder compile.** Current `OPENVINO_RELEASE_TORCH` frees only the 28+5 transformer `.layers`
   (~2.77 GiB for 1.7B). The original speech-tokenizer decoder remains resident even though
   `speech_tokenizer.decode` is patched to the OpenVINO vocoder. The reference encoder may also be
   dead after `voice_clone_prompt` is materialized. First instrument parameter/buffer bytes for
   tokenizer encoder and decoder separately; then replace only proven-dead parameters with empty
   storage, run `gc.collect()`/`malloc_trim`, and fail closed instead of retaining a silent PyTorch
   vocoder fallback. Validate prompt reuse, batch decode, streaming decode, RSS, parity, and
   listening. This is the most plausible steady-anonymous-memory reduction.
2. **Build a selective/thin serving loader.** Avoid materializing transformer blocks and
   reference-only components that OpenVINO replaces. This primarily reduces boot peak and load
   time because the core layers are already released after compile, but it may also reduce
   allocator retention. Preserve embeddings, norms, projections, codec/predictor heads, configs,
   and the exact `GenerationMixin` return contract. This is high complexity and must retain the
   normal full FP32 exporter path.
3. **Test BF16 activation hints and recognized state-cache precision independently.** The current
   OV config uses `INFERENCE_PRECISION_HINT=f32` and `KV_CACHE_PRECISION=f32`. On the now-stateful
   main, try BF16 inference precision and then `KV_CACHE_PRECISION=u8` as separate experiments.
   Record whether OpenVINO actually applies each property. The main FP32 cache is only roughly
   56*8*768*128*4 bytes (~176 MiB), so U8 cache savings are bounded (~132 MiB maximum) and cannot
   explain multi-GiB usage. Require deterministic token/cache parity, production listening, and
   latency/RSS results; do not silently lower thresholds.
4. **Capacity 512 experiment only if product duration permits.** The 2048 -> 768 change previously
   saved ~611 MiB peak. A further 768 -> 512 reduction may save only low hundreds of MiB and lowers
   context from ~64 to ~43 seconds including prompt/generated positions. Test long prompts and fail
   closed on overflow. Keep cap768 as the production candidate until evidence justifies the trade.
5. **Measure explicit predictor duplication.** The explicit predictor compiles prefill and decode
   graphs, potentially duplicating its small weights. A single stateful predictor can reduce graph
   duplication, but the earlier 1.7B decision favored explicit predictor; revisit only with measured
   memory/latency and all 15 codebook parity. Expected savings are modest.
6. **Do not optimize reclaimable file cache blindly.** OpenVINO weight mmaps legitimately populate
   file cache, which the kernel can reclaim. Copying IR, dropping caches globally, or disturbing
   unrelated host workloads is not acceptable. The operational issue is the cold/first-generation
   cgroup peak; solve anonymous duplication first and evaluate whether 10 GiB remains safe under
   concurrent host pressure. If the 20% peak-headroom rule is strict, 10 GiB is not yet sufficient.

Exact next tasks:

1. Commit/push this final documentation checkpoint.
2. Add model-free byte-accounting/release helpers for speech-tokenizer components, with synthetic
   unit tests. Do not release anything before measuring and identifying runtime consumers.
3. Run an isolated 1.7B A/B on `dockermisc1`: baseline versus tokenizer release, recreate the
   container between runs, reset/capture cgroup peak, and use the same deterministic and production
   prompts. Roll back immediately on decode/streaming failure.
4. Investigate the PyTorch rollback timeout separately. A bounded internal generation with a low
   `max_new_tokens` can diagnose functionality, but it does not make the public 300-second rollback
   gate pass. Do not increase the public timeout merely to turn the gate green.
5. Have the user perform blind listening on the saved 0.6B and 1.7B WAVs before selecting a model.

## 4. `src/qwen3_tts/app.py` — the merged Flask app (single port 8318)

ONE `app = Flask(__name__)`. Import the model module and call it directly. Endpoints (exact contracts,
taken from the old `app_api.py` + `app_worker.py`):

- `GET /health` → JSON `{status, backend, model, ...openvino info..., timestamp}`. Build it from
  `model` module state (loaded? backend? OV vocoder enabled?). No proxy, no "degraded".
- `POST /generate` body `{text, language?, response_format?}` → audio bytes. `text` required (400 if
  missing). Default `language="English"`, `response_format="mp3"`. Encode mp3→`audio/mpeg`,
  else wav→`audio/wav` (use `soundfile.write(buf, wav, sr, format=...)`).
- `POST /v1/audio/speech` body `{input, response_format?, model?, voice?, ref_audio?, ref_text?, ...}`
  → audio bytes. Map `input`→text (tolerate `text`). Missing input → **400 with OpenAI error
  envelope** `{"error":{"message","type":"invalid_request_error","code":null}}`. `voice`/`ref_*` are
  accepted but IGNORED (voice is server-side — see memory `hermes-tts-consumer`). Reuse the same
  encode path as `/generate`.
- `POST /generate/stream` body `{text, language?}` → headerless mono **f32le PCM** stream with headers
  `X-Audio-Format: f32le`, `X-Audio-Sample-Rate`, `X-Audio-Channels: 1`,
  `X-Stream-Error-Semantics: connection-close`. Calls the streaming generator in `model.py` directly
  (the old `/infer_stream` logic — a `queue.Queue` fed by a producer thread via the `ThreadPoolExecutor`,
  yielding PCM bytes). Requires the FP32 OpenVINO vocoder (503 if absent).
- KEEP the dev parity endpoints `POST /stream_internal` and `POST /batch_internal` (used by the A/B
  and validation). Same bodies/headers as the old worker versions. Mark them dev-only.

Helpers in `app.py`: `_openai_error(message, status, type)` and
`_encode(wav, sr, response_format) -> (bytes, media_type)`.
`if __name__ == "__main__": app.run(host="0.0.0.0", port=8318)`.

## 5. `src/qwen3_tts/model.py` — model load + generation (NO Flask)

Move the guts of the old `app_worker.py` here, minus the Flask routes:
- Module globals `model`, `voice_clone_prompt`, `ov_runtime`, `ov_metadata`, `ov_config`, and a
  `ThreadPoolExecutor(max_workers=1)` named `executor` (serialize inference).
- `load_model()` — same logic as old `app_worker.load_model()`, but read settings from
  `qwen3_tts.config` (see §6) instead of bare `os.getenv`. Inside it:
  `from qwen3_tts.openvino.talker import OVTalkerRuntime`.
- `_validate_ov_metadata`, `_run_generate`, `_run_generate_with_streaming`, `_apply_optional_seed`,
  `_trim_silence` — copy verbatim from old `app_worker.py` (they are correct).
- Import update: `from qwen3_tts.streaming import StreamingVocoderSession`,
  `from qwen3_tts.openvino.runtime_config import apply_thread_env` (call at import, before torch).
- Call `load_model()` at import time (as the old worker did) so gunicorn `-w 1` loads once.
- `app.py`'s `/generate/stream` imports `_run_generate_with_streaming`, `executor`, `ov_runtime`.

The old `app_worker.py`/`app_api.py` sources are in git history on `main` (and the squashed PR #68
commit `c5d082e`). Use them as the literal reference while writing model.py/app.py.

## 6. `presets.py` + `config.py` — replace the env maze

`presets.py`: a dict `MODEL_SIZE -> settings`. Source of truth = the working candidate values
(verified on dockermisc1):

| key | 0.6B | 1.7B |
|---|---|---|
| `model_repo` | `Qwen/Qwen3-TTS-12Hz-0.6B-Base` | `Qwen/Qwen3-TTS-12Hz-1.7B-Base` |
| `backend` | `openvino` | `openvino` |
| `main_compression` | `int8` | `int4` (group size 32) |
| `predictor_compression` | `int8` | `int8` |
| `vocoder` | FP32 OpenVINO, enabled | FP32 OpenVINO, enabled |
| `stateful_capacity` | 768 | 768 |
| `mem_limit / swap` | `10G / 11G` | `10G / 11G` |
| torch load dtype | `bfloat16`, low_cpu_mem | `bfloat16`, low_cpu_mem |

IR stable paths (the export step MUST emit these; presets reference them):
- `OV_MODEL_DIR                  = /ov/<SIZE>/ir`
- `OPENVINO_MAIN_STATEFUL_MODEL  = /ov/<SIZE>/main_stateful_cap768.xml`
- `OPENVINO_VOCODER_DIR          = /ov/<SIZE>/vocoder`
- (predictor stateful if used: `/ov/<SIZE>/predictor_stateful_cap32.xml`)

`config.py`: final settings = `preset(MODEL_SIZE)` overlaid with any explicit advanced env var (so
experts can still override). Expose accessors used by `model.py`. `REF_AUDIO` is always
`/voice/reference.wav` (mounted); `REF_TEXT` from env (required). Thread caps stay
`OMP/MKL/OV_INFERENCE_THREADS=6` (in `openvino/runtime_config.py:apply_thread_env`) — do not change.

## 7. Export tooling → `src/export/` (Phase 2)

`git mv` to `src/export/` (flat): `export_openvino.py`, `ov_export_wrappers.py`, `ov_stateful_cache.py`,
`parity_contract.py`, `calibration_capture.py`, `dump_audio.py`, `bench_common.py`,
`benchmark_vocoder.py`, `benchmark_tts.py`, `bench_speed.py`, `profile_tts.py`,
`test_vocoder_parity.py`, `test_transformer_parity.py`, `test_stateful_main_parity.py`,
`test_ov_generation.py`. They import each other by **bare name** (keep that; `src/export` is on
`PYTHONPATH`). Only rewrite imports of the **shared** modules:
- `from model_config import …`        → `from qwen3_tts.model_config import …`
- `import ov_runtime_config`          → `import qwen3_tts.openvino.runtime_config as ov_runtime_config`
- `from ov_talker_runtime import …`   → `from qwen3_tts.openvino.talker import …`
- `from ov_vocoder_runtime import …`  → `from qwen3_tts.openvino.vocoder import …`
- `from streaming_vocoder import …`   → `from qwen3_tts.streaming import …`

`scripts/export.py`: thin CLI that, given `MODEL_SIZE`, runs the existing export pipeline
(`export_openvino.py` → `scripts/transform_stateful_ir.py` for the stateful cap768 main, vocoder
export) and writes outputs to the stable `/ov/<SIZE>/…` paths in §6. `scripts/ab_test.sh`: run the
same text through 0.6B and 1.7B, save two WAVs.

## 8. Dockerfile / compose / .env / tests

- **Dockerfile:** `COPY src/ ./src/`, `COPY scripts/ ./scripts/`,
  `ENV PYTHONPATH=/app/src:/app/src/export`, `EXPOSE 8318` only, healthcheck on 8318,
  `CMD ["gunicorn","qwen3_tts.app:app","-w","1","-k","gthread","--threads","4","--timeout","300","--bind","0.0.0.0:8318","--log-level","info"]`
  (NO `--preload` — memory `serving-memory-footprint`). Exporter stage installs `requirements/export.txt`
  and runs `scripts/export.py`. Split old `requirements.txt`/`requirements-ov-*.txt` into
  `requirements/{runtime,openvino,export}.txt`.
- **compose.yml:** ONE service `qwen3-tts` (port 8318, MODEL_SIZE-driven, mem from preset, mounts
  `${REF_AUDIO_PATH}:/voice/reference.wav:ro`, model cache, `./data/ov:/ov`). A second service
  `export` under `profiles: [export]` running `scripts/export.py` into the same `./data/ov`. Only the
  3 user vars required; advanced vars commented.
- **.env.example:** `REF_AUDIO_PATH=`, `REF_TEXT=`, `MODEL_SIZE=0.6B`, then a commented advanced block.
- **tests/:** update imports to `qwen3_tts.*`. `tests/test_app_api.py` → point at merged `qwen3_tts.app`
  and mock the model functions instead of `requests`.

## 9. Docs (Phase 5)

`git mv` to `docs/dev/`: `OPENVINO_IMPLEMENTATION.md`, `OPENVINO_RESULTS.md`,
`PLAN_0.6B_STATEFUL_KV.md`, `PLAN_STREAMING_VOCODER.md`. Rewrite `README.md` → short quickstart +
links. Rewrite `HOW_TO_RUN.md`: §A user quickstart (the 4 commands), §B A/B test, §C advanced (export
internals, capacity tuning, pytorch fallback, memory) bridging the still-true facts from the old runbook.

## 10. VALIDATION GATE (Phase 6) — REQUIRED before "done"

You CANNOT run Python here (this Mac has no torch/flask/openvino). The ONLY real test is on
**dockermisc1** (`ssh dockermisc1`, sudo available). Touch ONLY `qwen3-tts*` containers; never blanket
`docker kill`/`stop`/`prune` — leave `litellm*`, `headroom-proxy`, `crowdsec`, hermes-*, *arr, etc.
running (memory `dockermisc1-ops`). Reference WAV on the box:
`/var/data/autopirate/qwen3-tts/voice/voice_A.wav`.

Gates (all must pass):
1. `python -m py_compile` over all new/moved `.py` (syntax only — does NOT prove imports).
2. Build the new runtime image on dockermisc1.
3. `docker compose run --rm export` for `MODEL_SIZE=0.6B` produces the `/ov/0.6B/...` IR.
4. `docker compose up`; `GET /health` ok; `POST /v1/audio/speech` (mp3 + wav) returns valid audio;
   `POST /generate` works; missing `input` → 400 OpenAI envelope.
5. A/B: repeat for `1.7B`; both produce audio; note latency + memory (~5.8 GiB steady for 1.7B).
6. Existing model-free unit tests pass: `python -m unittest` for the moved tests.

When ALL gates pass: commit in logical chunks, open a PR with a
`BEGIN_COMMIT_OVERRIDE`/`END_COMMIT_OVERRIDE` block (memory `pr-commit-override-block`), end commit
messages with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Only THEN mark complete.

## 11. Hard rules (from memory; keep in effect)

- Never blanket `docker kill/stop/prune`; only `qwen3-tts*` benchmark containers.
- Never run two large model jobs at once on the 15 GiB box (OOM).
- Worker gunicorn: `-w 1`, **never** `--preload` (wastes ~2.8 GiB).
- Do not change `load_model`'s exporter fp32 parity needs; serving uses bf16 via `OPENVINO_TORCH_DTYPE`.
- Keep `TTS_BACKEND=pytorch` rollback working.

---
*Prior streaming-validation handoff (now merged as v0.14.0) is preserved in git history and in
`docs/dev/OPENVINO_RESULTS.md`.*
