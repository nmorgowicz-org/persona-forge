# Pocket-TTS Zero-Friction Artifacts and ONNX Runtime Plan

**Status:** Track A implemented and committed on branch `pocket-tts-ungated-onnx` (resolver, English config, runtime wiring, health provenance, tests, docs) and passing local validation; no PR per user instruction. Remaining: CI image smoke test via `ready-to-test`, and the §8.7 live acceptance on `docker-agent`. Track B remains gated by evidence (updated 2026-08-23)

**Date:** 2026-07-13  
**Primary runtime:** Pocket-TTS on CPU-only Linux AMD64  
**Primary host:** `docker-agent`
**Current package:** `pocket-tts==2.1.0`

## 1. Objective

Make Pocket-TTS arbitrary voice cloning work for a normal home user without requiring them to
create a Hugging Face account, accept a gate, or configure `HF_TOKEN`, while preserving source
provenance, model integrity, the official authenticated path, and a built-in-voice degraded mode.

Then evaluate a project-controlled ONNX runtime that may reduce startup friction, Torch coupling,
steady RSS, and CPU latency without changing voice identity, intelligibility, prosody, EOS
behavior, or the repository's HTTP contracts.

The work is deliberately divided into two tracks:

- **Track A — zero-token standard runtime:** use the hash-identical LunaHR cloning checkpoint
  with verified provenance, then fall back to Kyutai's official gated checkpoint when an
  authenticated token is available, then degrade to Kyutai's official ungated built-in voices.
- **Track B — ONNX runtime:** reproduce and validate the Pocket-TTS graphs and generation loop,
  first in FP32 and then optionally INT8, before considering ONNX as the default engine.

Track A must not wait for Track B. Track B must not silently become the product default merely
because its models load or a short sample sounds plausible.

## 2. User Experience Target

The default setup should be:

1. Start the container.
2. Wait for the Pocket-TTS model to load.
3. Add or select a reference voice.
4. Generate cloned speech.

No normal-user step should require:

- A Hugging Face account.
- Accepting a model gate in a browser.
- Creating or copying an access token.
- Understanding checkpoints, safetensors, ONNX graphs, or cache directories.

Advanced users may still supply `HF_TOKEN` to prefer or recover from the official gated source.
Operators must be able to force a particular source or engine for diagnosis and rollback.

## 3. Current Upstream Behavior

Pocket-TTS 2.1.0's English config points at:

```text
cloning model:
hf://kyutai/pocket-tts/languages/english/model.safetensors
revision: 39592ff23c9ef80098bb74895d104c26275fe2c9

non-cloning fallback:
hf://kyutai/pocket-tts-without-voice-cloning/languages/english/model.safetensors
revision: d29db7978e464fb90cb3359ee0c69a273b9142cc
```

If the cloning download raises any exception, the package catches it and loads the non-cloning
checkpoint. The service can then synthesize using predefined voice states but cannot encode an
arbitrary WAV into a new voice state.

Built-in voices are already tokenless. Pocket-TTS 2.1.0 resolves them from:

```text
hf://kyutai/pocket-tts-without-voice-cloning/
  languages/english/embeddings/<voice>.safetensors
revision: e041936c75475d350b405bc870bcf7c22da4e9e6
```

The legacy `embeddings_v3/` layout contains 21 voices. The current
`languages/english/embeddings/` layout contains 26, adding `estelle`, `giovanni`, `juergen`,
`lola`, and `rafael`. Use the language-scoped layout for new work.

## 4. Provenance Snapshot

### 4.1 LunaHR standard checkpoint

Repository:

```text
lunahr/pocket-tts-ungated
repository revision: d03cd73415a8d46d8eb115c7b524aebb0a729f4a
```

The mirrored English cloning checkpoint matches Kyutai's artifact:

```text
path: languages/english/model.safetensors
size: 219,029,196 bytes
sha256: 473f47d99560bd50eb8b4509d3cacfe7f316ab20bdca86505403a2e6a936a6e9
```

Hugging Face reports the same file/blob identity and security-scan hash for the Kyutai and
LunaHR copies. The mirror also carries the tokenizer and precomputed voice-state safetensors.

The implementation must rely on the pinned revision and expected checksum, not on repository
popularity, mutable `main`, or an assumption that a third-party account will remain available.

### 4.2 Third-party ONNX bundle

Evaluation source:

```text
Hugging Face: KevinAHM/pocket-tts-onnx
repository revision: 58a6d00cf13d239b6748cb0769f35c580a8f606c

Exporter: KevinAHM/pocket-tts-onnx-export
reviewed head: b25d4a7d (2026-04-21)
```

The English bundle with the full manifest lives at `onnx/english_2026-04/` (matching
the package's `english_2026-04.yaml` config) and contains:

- `flow_lm_main.onnx` and `flow_lm_main_int8.onnx`.
- `flow_lm_flow.onnx` and `flow_lm_flow_int8.onnx`.
- `mimi_encoder.onnx` (and `_int8`) for arbitrary reference-audio cloning.
- `mimi_decoder.onnx` and `mimi_decoder_int8.onnx`.
- `text_conditioner.onnx` (and `_int8`).
- `tokenizer.model`.
- `bos_before_voice.npy`.
- `bundle.json` with explicit state manifests.

A root-level `onnx/` directory also holds bare English graphs (same model family,
slightly different sizes) without a `bundle.json` or `bos_before_voice.npy`. Other
languages live under `onnx/<language>/`.

The selected English INT8 execution set is approximately 165 MB on disk when the FP32 Mimi
encoder and text conditioner are retained. Do not download the entire multilingual repository
for an English-only deployment.

The third-party runtime is feasibility evidence, not yet an authoritative production artifact.
Its wrapper, exporter patches, graph hashes, and model behavior must be independently reviewed
and validated.

### 4.3 Fresh re-verification (2026-08-22)

Re-verified all of §3–§4.2 against live Hugging Face / GitHub / PyPI state (authenticated
API) immediately before Track A implementation:

- `pocket-tts==2.1.0` is still the latest PyPI release (uploaded 2026-05-04). The installed
  package's `config/english.yaml` matches §3's `hf://` paths and revisions exactly.
- Every pinned revision still exists and is stable: `kyutai/pocket-tts` remains gated
  (`gated=auto`); `lunahr/pocket-tts-ungated` `main` is still exactly the pinned
  `d03cd734` (no drift); `KevinAHM/pocket-tts-onnx` `main` is still `58a6d00c`; the exporter
  head is still the reviewed `b25d4a7d` (2026-04-21).
- File identities (HF-reported sha256, re-fetched 2026-08-22):
  - Cloning model, `languages/english/model.safetensors`: 219,029,196 bytes,
    `473f47d99560bd50eb8b4509d3cacfe7f316ab20bdca86505403a2e6a936a6e9` — hash-identical at
    `kyutai/pocket-tts@39592ff2` and `lunahr/pocket-tts-ungated@d03cd734` (confirms §4.1).
  - Non-cloning model, `languages/english/model.safetensors`: 219,029,196 bytes,
    `be9c6b4876d3f30740a8225dfcaa2e43dc4aeb753c15272735bee16bbb4abb0a` (identical at both
    pinned revisions) — pin this for the degraded built-in-only path.
  - Tokenizer, `languages/english/tokenizer.model`: 59,339 bytes,
    `d461765ae179566678c93091c5fa6f2984c31bbe990bf1aa62d92c64d91bc3f6` (identical across all
    three repositories) — pin this for explicit built-in voice resolution.
- The 26-voice `languages/english/embeddings/` layout is unchanged at `e041936c` and `main`,
  including exactly the five voices named in §3; `d29db79` still carries 21; `embeddings_v3`
  still carries 21. All 26 per-voice (size, sha256) pins are recorded in code, not in this
  plan: `VOICE_EMBEDDING_PINS` in `src/persona_forge/pocket_artifact_resolver.py` (verified
  2026-08-22).

## 5. Licensing and Use Constraints

- The Pocket-TTS model artifacts are marked CC-BY-4.0.
- The upstream and mirrored cards retain prohibited-use language covering unauthorized cloning,
  impersonation, fraud, deception, harmful content, and privacy-invasive use.
- The intended project use is personal/home and consensual sharing with friends or coworkers.
- Removing a download gate does not remove attribution, consent, or use obligations.
- Preserve model attribution in documentation and surfaced model metadata.
- Do not commit, bake, or redistribute weights through this Git repository or container image.
- Before publishing project-controlled converted artifacts, confirm the exporter code license,
  model attribution, model-card notices, and any upstream distribution obligations. Record that
  decision in the release documentation; do not infer it solely from a Hugging Face metadata tag.

This plan is technical guidance, not legal advice.

## 6. Non-Negotiable Runtime Invariants

- One heavy TTS engine resident at a time.
- One Gunicorn worker: `-w 1 -k gthread --threads 4`, never `--preload`.
- All model loading, voice encoding, generation, and engine swapping remain serialized through
  the existing `ThreadPoolExecutor(max_workers=1)`.
- Never load Torch Pocket-TTS and ONNX Pocket-TTS simultaneously for automatic fallback.
- A failed engine must be fully released before another engine is loaded.
- Preserve `/generate`, `/generate/with_metrics`, `/generate/async`, `/v1/audio/speech`,
  `/health`, voice-library selection, and output-format behavior.
- Preserve Pocket-TTS as the primary runtime and Qwen PyTorch/OpenVINO as explicit rollback
  backends.
- Keep model weights, ONNX graphs, reference audio, generated audio, tokens, and voice-state
  caches outside Git.
- Do not run export and the serving model simultaneously on `docker-agent`.

## 7. Target Architecture

Separate three concerns that are currently partly coupled:

1. **Artifact resolution:** where model files come from and how they are verified.
2. **Pocket engine:** standard Torch Pocket-TTS or the experimental ONNX runtime.
3. **Product adapter:** voice-library resolution, state caching, generation, post-processing,
   health, and endpoint compatibility.

Conceptually:

```text
PocketArtifactResolver
    -> verified local artifact set

PocketEngine protocol
    -> TorchPocketEngine
    -> OnnxPocketEngine

pocket_tts_runtime product adapter
    -> default/library/built-in voice selection
    -> persistent voice-state cache
    -> generate
    -> output trim/repair
    -> health and unload
```

The engine protocol does not need to become a broad framework. It should expose only the
capabilities the product already uses:

```text
load(config) -> engine
prepare_voice(reference | built_in | cached_state) -> voice_state
export_voice_state(voice_state, path)
import_voice_state(path) -> voice_state
generate(voice_state, text, generation_config) -> mono float audio + sample rate
unload()
```

Engine-specific tensors must not leak into `app.py`, `model.py`, or voice-library metadata.

## 8. Track A — Zero-Token Standard Pocket Runtime

### 8.1 Artifact resolution order

For cloning-model startup in automatic mode:

```text
1. verified project-local cache
2. LunaHR pinned ungated checkpoint
3. Kyutai official gated checkpoint, only when authentication is available
4. Kyutai official non-cloning checkpoint as degraded built-in-only mode
```

The exact policy should be configurable:

```text
POCKET_TTS_MODEL_SOURCE=auto | lunahr | official | local
POCKET_TTS_ARTIFACT_DIR=<persistent path>
```

Recommended semantics:

- `auto`: local verified cache, LunaHR, authenticated official, then non-cloning mode.
- `lunahr`: local cache or LunaHR; fail clearly if cloning cannot be obtained.
- `official`: local official cache or authenticated Kyutai; preserve upstream fallback behavior
  only when the operator explicitly accepts built-in-only degradation.
- `local`: network-free; require a verified local checkpoint.

Do not attempt the official gated URL without authentication on every startup merely to receive
an expected 401. This adds latency and produces confusing logs.

### 8.2 Project-owned artifact resolver

Resolve the file before constructing `TTSModel`:

1. Acquire a per-artifact file lock.
2. Check the dedicated persistent artifact location.
3. Stream a missing download into a temporary file on the same filesystem.
4. Enforce a reasonable maximum expected size.
5. Compute SHA-256 while downloading or immediately after download.
6. Reject and quarantine/delete any mismatched artifact.
7. Atomically rename the verified file into its final content-addressed path.
8. Return a local path, source identity, revision, and verified hash.

Do not execute remote code. Safetensors loading stays `safetensors`-only.

The default artifact directory should live under the persistent model cache, not under the voice
library or source tree. The final location must be documented and surfaced in health without
exposing credentials or private host paths unnecessarily.

### 8.3 Project-controlled English config

The standard Pocket package does not expose a model-repository override. Create a small,
versioned project English config matching Pocket-TTS 2.1.0, but replace the cloning
`weights_path` with the resolver's verified local path.

Keep the official ungated tokenizer and built-in voice states pinned to Kyutai's
`pocket-tts-without-voice-cloning` repository.

Loading through a project config changes Pocket-TTS's `origin`, so predefined names may no
longer pass its internal "official language config" check. The product adapter must resolve a
built-in name to the pinned official ungated safetensors URI or verified local file explicitly,
rather than depending on that internal shortcut.

Do not monkeypatch the installed package or construct Hugging Face cache internals manually.

### 8.4 Failure and integrity behavior

- A network failure may continue to the next configured source.
- A 401/403 from the official source means "authentication unavailable," not "license rejected"
  unless the response proves that distinction.
- A checksum mismatch is a security/integrity failure. Never load the file. Record the failed
  source and continue only to a separately pinned source.
- Never silently claim cloning is available after loading the non-cloning model.
- Preserve usable built-in speech when all cloning sources are unavailable, unless the operator
  explicitly selected a fail-closed source mode.
- Never print tokens, signed download URLs, request headers, or complete private cache paths.

### 8.5 Health and diagnostics

Add structured, non-secret fields under the Pocket runtime health/config surface:

```text
pocket_engine: torch
pocket_model_source: cache | lunahr | kyutai | kyutai_without_cloning
pocket_model_revision: <immutable revision>
pocket_model_sha256: <expected hash or abbreviated display plus full metrics value>
pocket_model_verified: true | false
pocket_cloning_available: true | false
pocket_cloning_status: ready | degraded | unavailable | integrity_error
```

Frontend messaging should be action-oriented:

- Normal zero-token success: no warning.
- Built-in-only degradation: explain that custom voice cloning is temporarily unavailable but
  built-in voices remain usable.
- Explicit official mode without token: instruct advanced users how to configure authentication.
- Integrity failure: report a model verification error, not a generic gated-token message.

### 8.6 Track A tests

Unit/fake tests must cover:

- Verified cache hit with no network call.
- Successful LunaHR download and hash verification.
- Partial download cleanup and atomic installation.
- Checksum mismatch rejection.
- Concurrent resolver calls using one download/file lock.
- LunaHR unavailable, official token present, official success.
- LunaHR unavailable, no token, built-in-only degradation.
- Forced `lunahr`, `official`, and `local` modes.
- Built-in voice loading through the official ungated repository.
- Arbitrary reference WAV voice-state creation.
- Persistent voice-state export, reload, and invalidation.
- Health provenance and secret redaction.
- Fake runtime parity for every new health/config field.

### 8.7 Track A live acceptance

On `docker-agent`:

1. Remove only the disposable test copy of the Pocket cloning artifact; do not delete unrelated
   Hugging Face or model caches.
2. Start with no `HF_TOKEN` and confirm LunaHR acquisition plus arbitrary voice cloning.
3. Restart network-free and confirm verified-cache startup.
4. Generate with the mounted reference, a voice-library voice, and a built-in voice.
5. Simulate LunaHR unavailability without modifying unrelated DNS/network configuration.
6. With an authorized token, confirm official fallback.
7. Without a token, confirm built-in-only degraded startup.
8. Confirm endpoint compatibility, async progress, output formats, and Pocket-TTS prosody repair.
9. Record load time, RSS, host RAM/swap, and generation latency against the current runtime.

Track A ships only after zero-token cloning, authenticated official fallback, and built-in-only
degradation all work from clean startup states.

### 8.8 Track A execution status (2026-08-23)

Implemented (branch `pocket-tts-ungated-onnx`, not yet committed):

- `src/persona_forge/pocket_artifact_resolver.py` — pinned catalog (3 core artifacts + 26
  built-in voice embeddings with size/SHA-256), stdlib-only `PocketArtifactResolver`
  (streaming size-capped download, hash-as-you-stream, per-artifact flock, atomic
  content-addressed install, corrupt-cache redownload, gated-source skip policy,
  secret-redacted errors), injectable `fetch` for tests.
- `src/persona_forge/pocket_english_config.py` — project-owned English config renderer
  (byte-for-byte pocket-tts 2.1.0 schema; the three downloadable paths rewritten to
  verified local files) + atomic writer under `<artifact_dir>/config/english-pf.yaml`.
- `src/persona_forge/pocket_tts_runtime.py` — English loads go through
  `_load_via_resolved_artifacts()` (`POCKET_TTS_MODEL_SOURCE` modes `auto`/`lunahr`/
  `official`/`local`, auto/official degrade to the pinned built-in-only model with
  `has_voice_cloning=False`, `local`/`lunahr` fail closed, tokenizer falls back to the
  package's public pin outside `local`); built-in voice names resolve to pinned local
  `.safetensors` and are passed as paths to `get_state_for_audio_prompt`; provenance dict
  (`pocket_tts_provenance`) persists across idle-unload. Non-English loads keep the legacy
  package-config path.
- `src/persona_forge/model.py` — `POCKET_TTS_MODEL_SOURCE` / `POCKET_TTS_ARTIFACT_DIR`
  passthrough (reload keys), `/health` gains `pocket_engine`, `pocket_model_source`,
  `pocket_model_revision`, `pocket_model_sha256`, `pocket_model_verified`,
  `pocket_cloning_available`, `pocket_cloning_status` (+ provenance-sourced message);
  legacy `voice_cloning_available` semantics unchanged.
- Tests: `tests/tier1_unit/test_pocket_artifact_resolver.py` (18 tests, model-free lane),
  `tests/tier1_unit/test_pocket_tts_runtime.py` extended (`TestResolvedArtifactLoading`,
  11 tests; legacy-path tests repointed to `french_24l`), `tests/tier2_backend/test_app_health.py`
  (+2 pocket provenance tests), `tests/fixtures/fake_runtime.py` parity block.
- Docs: `.env.example`, `compose.yml`, `docs/ENV_REFERENCE.md` (new
  "Pocket-TTS artifact sourcing" section), `docs/HOW_TO_RUN.md`,
  `docs/architecture/pocket_tts_integration.md` (new §9), this plan (§13/§4.2/§4.3).
- Frontend: unchanged — all health fields are additive; existing
  `voice_cloning_available` / `message` wiring in `store.ts` still works.

Local validation passed (2026-08-23): model-free pytest lane (482 passed),
`scripts/validate_repo.py`, `git diff --check`. One real bug found and fixed by the new
tests: `load_pocket_tts_model` was missing `global` for the cloning status fields, so
degraded-mode status never reached module state.

Independent re-validation (2026-08-23) found and fixed two additional small bugs:
`local` mode could still download the dormant non-cloning fallback entry (it is now
resolved cache-only, keeping `local` strictly network-free), and
`build_default_voice_state` overwrote the load-time degraded provenance message with the
generic gated-terms fallback when the default voice_state failed to build (the provenance
message is now preserved). Re-validated: model-free lane 482 passed, torch lane 426
passed, `scripts/validate_repo.py`, `git diff --check`, `docker compose config --quiet`,
import smoke (29-artifact catalog), and strict `load_config` acceptance of the rendered
project config.

Execution log (2026-08-23): committed and pushed on `pocket-tts-ungated-onnx` as a single
Conventional Commit; no PR, per user instruction. Field observation on `docker-agent`
(image `v1.1.4`, pre-Track A): after a `LOW_RAM_MODE` idle-unload, the legacy
`voice_cloning_available` flag (in-memory default voice_state presence) reported `false`
with the generic "set an HF_TOKEN" message although the gated model was cached, the token
valid, and a live generation request succeeded via transparent reload. The provenance-backed
`pocket_cloning_status` / `pocket_cloning_available` fields fix this class of false warning;
confirm in the §8.7 acceptance.

Remaining before Track A ships:

1. CI image build + import smoke test via `ready-to-test` (no dependency changes in this
   pass, but the new modules must import cleanly in the image).
2. §8.7 nine-step live acceptance on `docker-agent` (zero-token LunaHR acquisition,
   verified-cache restart, degraded + official paths, metrics capture).

## 9. Track B — ONNX Feasibility and Eventual Runtime

### 9.1 Initial strategy

Use KevinAHM's exporter and English bundle as a reference implementation. Do not import remote
Python at runtime. Review and vendor/fork only the minimum code needed for a reproducible export
and project-owned adapter.

The experiment should answer two separate questions:

1. Can FP32 ONNX reproduce the pinned Torch Pocket-TTS computation and product behavior?
2. If yes, does ONNX FP32 or INT8 provide enough latency, RSS, deployment, or streaming benefit
   to justify another engine?

A "yes" to export feasibility is not automatically a "yes" to shipping ONNX.

### 9.2 Artifact identity and layout

Define an immutable artifact ID containing at least:

```text
pocket package version
source checkpoint revision and sha256
exporter source revision
ONNX opset(s)
ONNX Runtime version
language/config signature
precision
state-cache capacity/layout
```

Store generated graphs outside Git under a dedicated persistent directory, for example:

```text
${MODEL_CACHE_PATH}/pocket_tts_onnx/<artifact-id>/
```

Each artifact directory requires a machine-readable manifest with:

- All source revisions.
- Config signature.
- Graph filenames and SHA-256 values.
- Input/output names, shapes, and dtypes.
- Explicit state manifest.
- Precision and quantization settings.
- Export command and tool versions.
- Validation status.

No model files or benchmark audio enter Git or the container image.

### 9.3 Export behavior to reproduce

The project-owned exporter/runtime must preserve or explicitly reimplement:

- Mimi reference-audio encoding and speaker projection.
- BOS-before-voice handling.
- Text normalization and tokenization.
- FlowLM conditioning prefill.
- Autoregressive FlowLM state updates.
- EOS-logit calculation and configurable threshold.
- Temperature and random-noise generation.
- Optional noise clamp.
- Configurable LSD/Euler integration steps.
- Frames retained after EOS.
- Mimi state reset per utterance and streaming decode updates.
- Sentence/chunk behavior for long text.
- Current post-EOS energy trim and shared output-polish/prosody-repair path.
- Voice-state import, export, persistence, and invalidation.

The following Kevin wrapper defaults are not product requirements and should be parameterized or
replaced:

- Hard-coded EOS threshold of `-4.0`.
- Different default temperature and LSD steps.
- Wrapper-owned sentence splitting and short-input padding.
- In-memory-only cache for newly encoded arbitrary voices.
- Built-in voice downloads hard-coded to the gated Kyutai repository.

### 9.4 Export risks requiring explicit gates

#### Stateful cache conversion

Pocket-TTS contains stateful streaming attention and convolution modules. ONNX makes their
caches, offsets, counters, and first-frame flags explicit. Validate:

- State initialization.
- Prefill increments.
- Every autoregressive update.
- Maximum sequence capacity.
- Utterance reset.
- Mimi decoder reset and chunk carry-over.
- No cross-request or cross-voice contamination.

Kevin's exporter monkeypatches attention, convolution, padding, and state increment behavior to
make tracing possible. Review every patch against the pinned Pocket-TTS 2.1.0 source. Component
parity at one synthetic step does not prove multi-step correctness.

#### Random sampling

The reference runtime uses Torch RNG while the third-party ONNX wrapper uses NumPy RNG. Matching
numeric seed values will not generally produce the same noise or waveform.

For parity testing, inject a pre-generated sequence of identical FP32 noise tensors into both
generation loops. Product RNG may remain engine-specific only after deterministic parity is
established and same-seed API expectations are documented.

#### Quantization

FP32 must pass before INT8 evaluation. Quantize graph families separately so quality loss can be
localized:

- FlowLM main.
- Flow network.
- Mimi decoder.
- Mimi encoder only if voice-similarity gates remain strong.
- Text conditioner only if transcript conditioning remains unchanged.

Do not accept whole-bundle INT8 solely because it is smaller or faster.

## 10. ONNX Validation Phases

### Phase B0 — Reproducible baseline

- Pin current Pocket-TTS package, English config, checkpoint, and runtime settings.
- Select committed benchmark prompts and non-Git reference audio.
- Record Torch FP32 and current Torch dynamic-INT8 behavior where supported.
- Capture load time, first generation, warm p50/p95, RTF, RSS, host RAM/swap, output duration,
  EOS step, and artifact sizes.
- Save same-seed WAVs outside Git for listening and later comparison.

### Phase B1 — Exporter audit and clean FP32 export

- Diff Kevin's vendored Pocket-TTS source/patches against `pocket-tts==2.1.0`.
- Remove unrelated code and network behavior.
- Export from the exact verified cloning checkpoint.
- Run `onnx.checker` and inspect graph inputs/outputs.
- Reject external-data paths that escape the artifact directory.
- Write the immutable artifact manifest.
- Confirm import with the repository's pinned ONNX Runtime on Python 3.13 Linux AMD64.

### Phase B2 — Component FP32 parity

Compare Torch against ONNX for:

- Text-conditioner output across short, punctuation-heavy, and long token sequences.
- Mimi encoder output across multiple sample rates and reference durations.
- Voice projection/BOS-prepend result.
- FlowLM conditioning prefill.
- EOS logits.
- Flow-network direction across multiple integration steps.
- Every explicit state tensor after prefill and after multiple decode steps.
- Mimi decoder audio and state across one-shot and multi-chunk decoding.

Record max/mean absolute error, p99/p99.9 error, SNR, cosine similarity where meaningful, state
shapes, and the first divergent step. Never catch missing outputs or relax thresholds merely to
complete the export.

Initial hypotheses, subject to ratification from the first clean FP32 run:

- Component tensor `rtol=2e-5`, `atol=2e-5` where scale makes that meaningful.
- Latent/hidden-state SNR at least 60 dB.
- Deterministic Mimi audio SNR at least 40 dB.
- No EOS decision divergence in bounded deterministic schedules.
- No state shape, counter, or reset mismatch.

### Phase B3 — Multi-step deterministic generation parity

- Feed identical reference embeddings, text tokens, and injected noise tensors.
- Compare prefill plus a bounded number of autoregressive frames.
- Carry Torch-owned and ONNX-owned state independently.
- Record the first divergent frame and component.
- Compare EOS logits and stop decisions without allowing one backend to drive the other.
- Decode identical latent prefixes through each Mimi decoder.
- Verify long-text chunk boundaries and state resets.
- Verify two sequential requests with different voices cannot contaminate each other.

Byte-identical final WAV is desirable but not required if deterministic latent and decoder gates
pass. Any audible difference remains a failure until explained.

### Phase B4 — Voice-state compatibility

- Load current standard Pocket `.safetensors` voice states in ONNX.
- Encode the same reference WAV through Torch and ONNX Mimi encoders.
- Compare embeddings and resulting conditioned state.
- Define a project-owned ONNX voice-state safetensors schema with version, engine artifact ID,
  source-audio hash, shapes, and dtypes.
- Export, reload, generate, and invalidate states.
- Confirm a voice edited or deleted from the voice library cannot continue through stale memory or
  disk caches.
- Decide whether standard and ONNX states are truly interchangeable; if not, keep format/version
  boundaries explicit and rebuild from the retained reference WAV.

### Phase B5 — FP32 end-to-end quality

Use representative prompts:

- One to five words.
- Multi-sentence paragraph.
- Punctuation and questions.
- Numbers, abbreviations, and uncommon words.
- Boundary-aware prosody repair prompts.
- Long text crossing the chunk threshold.

Use representative voices:

- Multiple official built-ins.
- Mounted default reference.
- Several consented voice-library references.
- Short and long reference clips.
- Quiet, energetic, accented, and breathy references.

Record:

- Human blinded A/B preference and defect notes.
- Speaker similarity using a pinned, documented embedding metric.
- ASR transcript/WER or transcript-match score using a provider pinned independently of the
  engine under test.
- Duration ratio.
- Loudness, clipping, DC offset, spectral anomalies, leading/trailing silence, and mid-utterance
  gaps.
- EOS frame and repair outcome.

FP32 ONNX must not regress intelligibility, speaker identity, naturalness, or boundary behavior.

### Phase B6 — Performance benchmark

Run one engine at a time on `docker-agent`. Compare:

1. Current Torch FP32.
2. Current Torch quantized mode if supported and stable.
3. ONNX FP32.
4. ONNX INT8 candidates that passed quality gates.

Measure:

- Artifact download and disk size.
- Cold load and verified-cache load time.
- Reference voice encoding time.
- Cached voice-state load time.
- Time to first audio where streaming is evaluated.
- End-to-end p50/p95 over at least five warm runs.
- RTF and output duration.
- Container RSS before load, after load, at peak generation, and after unload/trim.
- Host available RAM and swap.
- CPU utilization, thread count, and oversubscription.
- Pocket generation with alignment/prosody repair disabled and enabled.

Record host contention and use the same prompts, seeds/noise schedule, voice state, thread settings,
and post-processing configuration across engines.

Suggested promotion hypothesis: ONNX should provide at least a material latency or RSS benefit
(for example, roughly 1.25x warm latency improvement or a clearly useful memory reduction) without
quality loss. This is not a waiver: measured evidence and product value determine acceptance.

### Phase B7 — INT8 characterization

- Begin from the validated FP32 artifact.
- Quantize one graph family at a time.
- Repeat component, deterministic generation, voice similarity, listening, and performance gates.
- Keep Mimi encoder FP32 unless evidence supports quantizing it; voice identity is more important
  than a small reference-encoding speedup.
- Keep any graph FP32 when INT8 gives negligible speed/RSS benefit or audible degradation.
- Record the final mixed-precision manifest rather than labeling the entire runtime simply INT8.

### Phase B8 — Product integration behind an opt-in engine

Add:

```text
POCKET_TTS_ENGINE=torch | onnx | auto
POCKET_TTS_ONNX_PRECISION=fp32 | int8 | mixed
POCKET_TTS_ONNX_ARTIFACT_DIR=<persistent path>
```

Initially:

- Default remains `torch`.
- `onnx` fails clearly if its verified artifact is unavailable or invalid.
- `auto` may try ONNX only after ONNX has passed all promotion gates.
- Engine fallback occurs at model startup/reload, never midway through a request.
- Failed engine resources are released before fallback.

Preserve current Pocket controls:

- `POCKET_TTS_TEMP`.
- `POCKET_TTS_LSD_DECODE_STEPS`.
- `POCKET_TTS_EOS_THRESHOLD`.
- `POCKET_TTS_FRAMES_AFTER_EOS`.
- `POCKET_TTS_NOISE_CLAMP`.
- Output post-processing and boundary-aware prosody repair.

Update fake runtime parity and health to expose engine, precision, artifact identity, source,
verification, and fallback reason.

### Phase B9 — Fault-injection and fallback validation

Test clean startup for:

- Verified local ONNX artifact.
- Missing ONNX bundle with standard LunaHR checkpoint available.
- Corrupt ONNX graph with valid standard checkpoint available.
- ONNX session-construction failure.
- LunaHR unavailable with authenticated official checkpoint available.
- Both cloning sources unavailable, built-in-only mode available.
- Fully offline startup with all required artifacts cached.
- Forced `onnx`, `torch`, and `local` modes.

Automatic fallback must be bounded and deterministic. It must not repeatedly download, oscillate
between engines, hide integrity failures, or leave two models resident.

### Phase B10 — Default promotion and rollback

Promote ONNX to `auto` preference only after:

- All FP32 and selected-precision parity gates pass.
- Blinded listening finds no material regression.
- Voice similarity and intelligibility pass.
- Warm p95, RTF, load time, and RSS are recorded and justify the change.
- All endpoint, voice-library, async, repair, idle-unload, and engine-swap tests pass.
- Zero-token clean installation works.
- Standard Torch startup and generation are revalidated as rollback.

Rollback remains:

```text
POCKET_TTS_ENGINE=torch
POCKET_TTS_MODEL_SOURCE=lunahr | official | local
```

Keep Torch fallback for at least one release after ONNX promotion.

## 11. Benchmark Assets and Reports

May be committed:

- Text prompts.
- Synthetic/non-sensitive audio recipes.
- Corpus manifests without private paths.
- Benchmark harnesses.
- Sanitized JSON schemas and aggregate reports.
- Expected artifact hashes and provenance manifests.

Must remain outside Git:

- Model safetensors and ONNX graphs.
- Original reference voices.
- Generated comparison audio.
- Tokens and signed URLs.
- Private absolute paths.

For every benchmark report, record:

- Source commit and container/image identity.
- Pocket package and engine revision.
- Model/artifact revision and hashes.
- Runtime/precision/thread settings.
- Prompt and non-private voice identifier/hash.
- Seed or injected-noise schedule.
- EOS, frames-after-EOS, temperature, LSD steps, noise clamp, and post-processing settings.
- Host load, available RAM, swap, and unrelated contention.
- Exact commands and non-Git artifact locations.

## 12. Repository and Container Validation

Repository changes must run:

```bash
python scripts/validate_repo.py
docker compose config --quiet
git diff --check
```

Use `.venv/bin/python -m pytest`. The fake lane must remain model-free:

```bash
PYTHONPATH=src:src/export .venv/bin/python -m pytest \
  -m "not slow and not requires_torch and not requires_model_weights and not requires_openvino_ir" \
  -n auto --tb=short \
  tests/tier1_unit tests/tier2_backend tests/tier3_api_integration
```

Container/dependency changes require the Linux AMD64 image build and import smoke test. Real model
parity, export, quality, and performance belong on `docker-agent`.

Frontend changes, if health/degraded messaging is surfaced, require:

```bash
npm run --prefix frontend check
npm run --prefix frontend build
```

## 13. Deployment Procedure

Permanent changes follow the development bind-mount workflow on `docker-agent`
(AGENTS.md, Development section):

```bash
cd ~/projects/persona-forge && git pull origin <branch>
cd frontend && npm run build
ssh docker-agent "docker compose -f ~/docker/docker-agent/docker-compose.yml \
  -f ~/docker/docker-agent/docker-compose.persona-forge-dev.yml \
  up -d --force-recreate persona-forge"
```

or simply run `scripts/dev-deploy.sh <branch>` on docker-agent (builds the frontend
and recreates with the dev override). Only recreate `persona-forge`. Never disturb
unrelated containers. Wait for `service_started=true` and `model_loaded=true`
before judging health. Do not misinterpret transitional startup state as a
gated-token failure.

## 14. Documentation Deliverables

Track A implementation must update:

- `.env.example` and `compose.yml`.
- `docs/ENV_REFERENCE.md`.
- `docs/HOW_TO_RUN.md`.
- `docs/architecture/pocket_tts_integration.md`.
- Health/API reference for new provenance fields.
- Troubleshooting text that distinguishes network, authentication, integrity, and degraded mode.

Track B implementation must additionally document:

- Export command and artifact manifest.
- Engine and precision selection.
- Model cache location.
- FP32/INT8 validation results.
- Performance and listening evidence.
- Standard-engine rollback.

## 15. Recommended Execution Order

1. Implement Track A's artifact resolver, project English config, explicit built-in resolution,
   health provenance, tests, docs, and live zero-token validation.
2. Ship Track A with the standard Torch Pocket engine still primary.
3. Establish the pinned Torch benchmark and quality corpus for Track B.
4. Audit/reproduce the FP32 ONNX export.
5. Complete component and multi-step parity.
6. Complete voice-state compatibility and end-to-end quality.
7. Benchmark FP32.
8. Characterize selective INT8 only if FP32 passes.
9. Integrate ONNX behind `POCKET_TTS_ENGINE=onnx`.
10. Validate fault injection and standard-engine rollback.
11. Promote ONNX to `auto` preference only if the evidence justifies it.

The next implementation session should begin with Track A. It is the smallest change that solves
the user-facing token/gate problem while retaining the current, already-validated Pocket-TTS
generation engine.
