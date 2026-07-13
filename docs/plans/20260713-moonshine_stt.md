# Moonshine STT Evaluation and Integration Plan

**Status:** Proposed exploration; no runtime change approved yet  
**Date:** 2026-07-13  
**Primary target:** CPU-only Linux AMD64 on `dockermisc1`  
**Current baseline:** `faster-whisper` `tiny.en`, CPU INT8

## 1. Purpose

Evaluate whether Moonshine can replace `faster-whisper` for the repository's short-form
speech-recognition tasks while improving latency and/or transcript quality without weakening
the existing speech-quality gates.

This is an ASR evaluation, not part of the completed boundary-aware prosody work. The prosody
aligner remains the pinned, project-owned MMS CTC ONNX implementation; it does not use Whisper
and is outside this plan.

The initial outcome may be one of three choices:

1. Keep `faster-whisper` because it remains the best operational fit.
2. Adopt Moonshine for all current ASR call sites.
3. Use different ASR providers for transcript bootstrap and generated-take validation if the
   evidence shows that their requirements differ materially.

## 2. Current Repository Use of STT

`src/qwen3_tts/asr_check.py` lazily loads `faster-whisper` `tiny.en` with:

- CPU execution.
- INT8 compute.
- English language selection.
- Greedy decoding (`beam_size=1`).
- `condition_on_previous_text=False`.
- Faster-Whisper's built-in VAD filter.

That implementation currently serves three related but distinct jobs:

### 2.1 Reference transcript bootstrap

`model.py` calls `transcribe_reference_audio()` when reference audio is mounted without an
explicit transcript and `REF_TEXT_AUTO` permits automatic transcription. The result becomes a
draft for review, not unquestioned ground truth.

### 2.2 Reference transcript validation

`app.py` and `model.py` call `validate_reference_text()` to compare a supplied reference text
with the recognized speech. The repository uses a deliberately tolerant in-order word-match
score to identify severe mismatches without penalizing ordinary ASR variations.

### 2.3 OmniVoice candidate validation

`omnivoice_engine.py` calls `has_speech()` after the cheap spectral/audio checks have passed.
This rejects dead air, effects, noise, or badly generated candidates that do not contain usable
speech. The transcript and Faster-Whisper `avg_logprob` also contribute to soft quality and
expected-text decisions.

These jobs do not currently provide live microphone transcription or a general transcription
API. Most inputs are short, already-recorded utterances. Moonshine's streaming design is useful
future headroom, but streaming alone is not a sufficient reason to migrate.

## 3. Why Evaluate Moonshine

[Moonshine Voice](https://github.com/moonshine-ai/moonshine) is an on-device speech toolkit
built around a portable C++ core and ONNX Runtime. Its current model family is designed to avoid
Whisper's fixed 30-second input window and, for streaming models, reuse encoder/decoder work as
audio arrives.

Relevant English models reported by the project as of 2026-07-13 include:

| Candidate | Parameters | Reported OpenASR average WER | Intended role |
| --- | ---: | ---: | --- |
| Tiny | 26M | 12.66% | Small offline model |
| Tiny Streaming | 34M | 12.00% | Footprint-oriented streaming model |
| Base | 58M | 10.07% | Higher-quality offline model |
| Small Streaming | 123M | 7.84% | Strong quality/latency balance |
| Medium Streaming | 245M | 6.65% | Highest reported English quality |

The published latency comparison reports Tiny Streaming at 69 ms and Small Streaming at
165 ms on Linux x86, compared with 1,141 ms for Whisper Tiny. These are upstream measurements,
not measurements from this repository or `dockermisc1`, and must not be treated as local
acceptance evidence.

Important upstream caveats:

- The headline WER values use floating-point reference models.
- The downloadable runtime models are quantized `.ort` files and can have higher WER,
  particularly at the Tiny size.
- Moonshine is optimized for live speech; its own documentation notes that other libraries may
  be preferable for bulk/batched offline transcription.
- The Python package and English models are MIT licensed. Non-English Moonshine models use a
  separate community/non-commercial license and are outside the initial English-only scope.

Moonshine is a better candidate for this CPU service than NVIDIA Canary 180M Flash. Canary's
published throughput is measured with large batches on NVIDIA A100/H100 GPUs and requires the
substantially larger NeMo dependency stack. Canary can be reconsidered if the deployment target
changes to GPU-backed batch transcription.

## 4. Scope and Non-Goals

### In scope

- English short-form transcription.
- Reference-audio transcript bootstrap.
- Reference transcript mismatch detection.
- OmniVoice generated-take speech and transcript validation.
- CPU latency, memory, packaging, and model-cache behavior.
- A reversible provider selection with Faster-Whisper retained as the baseline and rollback.

### Not in scope

- Replacing the MMS CTC forced aligner.
- Adding a public general-purpose STT endpoint.
- Live microphone UI or streaming transcription UX.
- Diarization, translation, or multilingual rollout.
- Replacing Pocket-TTS or another TTS backend.
- Adopting Moonshine's TTS/ZipVoice functionality as part of the ASR decision.
- Removing Faster-Whisper before Moonshine passes the real-audio gates.

## 5. Proposed Architecture Seam

Introduce a small internal ASR provider boundary rather than spreading Moonshine-specific calls
through `model.py`, `app.py`, and `omnivoice_engine.py`.

The provider should accept normalized mono audio and return a backend-neutral result similar to:

```python
AsrResult(
    has_speech: bool,
    transcript: str,
    confidence: float | None,
    confidence_kind: str | None,
    segments: list[AsrSegment],
    backend: str,
    model: str,
)
```

The exact representation is an implementation decision, but these principles are binding for
the experiment:

- Keep one lazy-loaded ASR model instance per process.
- Do not initialize ASR at module import time.
- Preserve serialized model access and existing single-process runtime invariants.
- Normalize audio consistently to 16 kHz mono before provider-specific inference.
- Keep transcript normalization and `compute_transcript_match_score()` backend-neutral.
- Treat provider confidence as optional. Moonshine must not be forced into Whisper's
  `avg_logprob` semantics.
- Preserve current endpoint and metadata fields during the experiment, including the legacy
  `whisper_transcript` field. Any rename to `asr_transcript` requires a separately reviewed API
  compatibility plan.
- A missing optional ASR dependency must fail predictably. It must not produce a later
  `None.transcribe()` error or silently weaken a configured fail-closed validation path.

Suggested experimental configuration:

```text
ASR_BACKEND=faster_whisper | moonshine
ASR_MODEL=tiny.en | tiny-streaming | base | small-streaming
```

Exact Moonshine model identifiers should be taken from the pinned package version rather than
invented from display names. The shipped default remains `faster_whisper` until the migration
gates pass.

## 6. Candidate Strategy

Benchmark the following candidates first:

1. `faster-whisper tiny.en` CPU INT8: authoritative baseline.
2. Moonshine Tiny Streaming: closest model-size comparison and likely latency floor.
3. Moonshine Base: modest footprint with better reported offline accuracy.
4. Moonshine Small Streaming: likely quality/latency choice if its RSS is acceptable.

Do not start with Medium Streaming. Add it only if Small fails the transcript-quality target and
the measured memory budget leaves enough headroom. Avoid evaluating many nearly equivalent
models before the corpus and measurement harness are trustworthy.

## 7. Evaluation Corpus

Use a labeled corpus that represents product decisions, not only standard ASR benchmarks.
Benchmark prompts and non-sensitive synthetic recipes may be committed. Reference voices,
generated speech, model weights, and benchmark audio must remain outside Git.

Record the corpus manifest with stable IDs, hashes, duration, sample rate, expected transcript,
category, and human disposition. Do not include private audio paths in committed output.

Minimum categories:

### Valid speech

- Clean English speech from multiple speakers.
- Short utterances of one to five words.
- Typical reference clips of five to thirty seconds.
- Accents and speaking styles represented by actual product use.
- Quiet, breathy, energetic, and rapidly spoken material.
- Pocket-TTS, Qwen3-TTS, and OmniVoice-generated speech.

### Transcript mismatch

- Exact transcript matches.
- Minor punctuation, contraction, filler, and article differences.
- Partial matches that should warn but remain recoverable.
- Severe mismatches that must fail.
- Reordered, repeated, truncated, and hallucinated phrases.

### Non-speech and degraded candidates

- Digital silence and room tone.
- Broadband and narrowband noise.
- Music and sound effects.
- Non-speech vocalizations.
- Clipping, dropouts, codec damage, and very low SNR.
- Known bad OmniVoice candidates retained outside Git.
- Speech mixed with noise, so the test does not reward rejecting every difficult input.

Human labels should describe the product decision (`accept`, `warn`, `reject_no_speech`, or
`reject_mismatch`) in addition to the literal transcript. Those decision labels are the primary
gate; WER alone is not.

## 8. Measurements

### 8.1 Correctness and product decisions

For each provider/model, record:

- Transcript text.
- Normalized WER and, where useful, CER.
- Existing in-order transcript-match score.
- Speech/no-speech decision.
- Final product disposition after current thresholds.
- False acceptance rate for non-speech or unusable candidates.
- False rejection rate for valid speech.
- Warn/fail confusion matrix for transcript validation.
- Decision disagreement against both human labels and the Faster-Whisper baseline.

False acceptance of unusable OmniVoice output is the highest-risk regression. Aggregate WER
must not hide a worse non-speech gate.

### 8.2 Performance

Measure on `dockermisc1` with Pocket-TTS as the primary runtime context:

- Dependency/model download size.
- ASR model initialization time.
- First-inference latency.
- Warm p50 and p95 latency by duration bucket.
- Real-time factor.
- Process/container RSS before load, after load, and after repeated inference.
- Host available RAM and swap before and after the run.
- CPU utilization and thread count.
- Effect on Pocket-TTS generation latency while ASR remains resident.

Run candidates one at a time from the same clean container/runtime state. Do not co-load several
ASR candidates and attribute their combined RSS to one model.

### 8.3 Operational behavior

Confirm:

- Linux AMD64 and Python 3.13 wheel/import compatibility.
- CPU-only execution with no CUDA libraries or GPU assumptions.
- Whether `moonshine-voice` bundles a native ONNX Runtime that conflicts with the repository's
  pinned `onnxruntime` package.
- Whether its required `sounddevice` dependency introduces a PortAudio/native-library runtime
  requirement even though server-side microphone capture is unused.
- Model cache paths, offline startup behavior, and revision pinning.
- Clean startup when the model is cached and a clear failure when it is unavailable.
- ASR state cleanup during idle unload/backend swaps if retaining it materially affects the
  repository's memory targets.

Before implementing model lifecycle changes, re-read
`docs/dev/architecture/OPENVINO_IMPLEMENTATION.md` and
`docs/agent-reference/RUNTIME_AND_MEMORY.md`.

## 9. Test and Validation Plan

### Phase A: Reproducible benchmark harness

- Add a non-production harness that can run one provider/model over the labeled manifest.
- Produce JSON/CSV measurements outside Git or in a deliberately sanitized report.
- Pin input ordering, warm-up count, repetition count, and thread settings.
- Verify transcript normalization and metric calculations with unit tests.
- Establish Faster-Whisper baseline results before adding Moonshine.

### Phase B: Packaging feasibility

- Install a pinned `moonshine-voice` version in a disposable local/container environment.
- Confirm Python 3.13 Linux AMD64 import and inference.
- Inspect dependency and native-library changes.
- Download models to the persistent model/cache volume, never the image or repository.
- Record exact package version, model identifier/revision, hashes, and disk usage.

### Phase C: Offline comparison

- Run the complete corpus through the baseline and initial Moonshine candidates.
- Compare decision accuracy before optimizing thresholds.
- Inspect every false acceptance and false rejection manually.
- Select at most one Moonshine candidate for integration.
- Document whether confidence-based soft rejection can be retained, replaced with another
  calibrated signal, or must remain provider-specific.

### Phase D: Provider integration behind a default-off switch

- Add the internal provider seam and Moonshine adapter.
- Keep `ASR_BACKEND=faster_whisper` as the default.
- Update fake runtime coverage for any health/config/API surface touched.
- Add focused tests for lazy loading, unavailable dependencies, empty audio, resampling,
  transcript results, and backend selection.
- Preserve current public response shapes.

### Phase E: Live target-host validation

- Deploy only to the `qwen3-tts` development container with bind mounts.
- Wait for Pocket-TTS to finish loading before collecting health or memory evidence.
- Run reference bootstrap, reference validation, and OmniVoice candidate validation end to end.
- Measure Pocket-TTS generation before and after ASR load.
- Confirm no unrelated container is restarted or disturbed.

### Phase F: Default decision

- Promote Moonshine only if all acceptance gates pass.
- Otherwise retain Faster-Whisper and preserve the benchmark evidence for later model releases.
- If promoted, keep the Faster-Whisper backend available for at least one release as rollback.
- Update environment documentation, architecture documentation, dependency notes, and the
  validated target-host measurements in the same change.

## 10. Proposed Acceptance Gates

Exact numeric limits should be finalized after the Faster-Whisper baseline run, but the migration
must satisfy all of the following:

### Required

- No increase in false acceptance of labeled non-speech/unusable OmniVoice candidates.
- No material increase in false rejection of valid speech.
- Reference mismatch decisions remain at least as accurate as the baseline against human labels.
- Transcript bootstrap quality is not worse on representative reference clips.
- Warm p95 ASR latency improves materially or a documented quality improvement justifies any
  regression.
- ASR RSS does not threaten Pocket-TTS operation or the host's no-swap steady-state target.
- No CUDA dependency, model artifact, reference audio, or generated audio enters Git or the
  image.
- Cached/offline startup and Faster-Whisper rollback both work.
- Existing API response contracts remain compatible.

### Suggested initial performance targets

Use these as hypotheses, not as substitutes for baseline evidence:

- At least 2x lower warm p95 latency than Faster-Whisper Tiny on the short-input corpus.
- No more than 250 MiB additional steady RSS versus the Faster-Whisper baseline for the selected
  Moonshine candidate.
- No measurable Pocket-TTS generation p95 regression beyond normal benchmark variance when ASR
  is idle but resident.

If Moonshine wins only on streaming latency, do not promote it until a product streaming use case
exists.

## 11. Repository Validation for an Implementation

Use `.venv/bin/python -m pytest` for repository tests. At minimum:

```bash
python scripts/validate_repo.py
git diff --check
PYTHONPATH=src:src/export .venv/bin/python -m pytest \
  -m "not slow and not requires_torch and not requires_model_weights and not requires_openvino_ir" \
  -n auto --tb=short \
  tests/tier1_unit tests/tier2_backend tests/tier3_api_integration
```

Dependency/container changes also require a Linux AMD64 image build and import smoke test. Real
ASR model runs and performance measurements belong on `dockermisc1`, with model artifacts and
audio outside Git. Validate the Faster-Whisper rollback path using the same corpus and runtime
settings.

## 12. Risks and Open Questions

- Does Moonshine's high-level VAD behave well on synthesized speech artifacts and non-speech
  effects, or should the repository retain its existing cheap first-pass analysis and use a
  provider-neutral ASR speech decision?
- What confidence information, if any, is stable enough to replace Faster-Whisper
  `avg_logprob`? A new value must be calibrated; it must not reuse `ASR_SOFT_LOGPROB` by name or
  numeric threshold without evidence.
- Does the packaged native runtime coexist cleanly with the repository's pinned ONNX Runtime and
  Python 3.13 stack?
- Is Tiny Streaming's quantized accuracy sufficient, or does Small Streaming provide the first
  meaningful quality improvement?
- Is Base preferable for the current offline workload despite the future flexibility of a
  streaming model?
- Should ASR remain resident after first use, participate in idle unload, or be unloaded around
  heavy backend swaps? Decide from measured RSS and reload cost.
- If a future live-STT UI is approved, can the provider seam support incremental state without
  changing the existing offline call sites?

## 13. Recommended Next Step

Build only the benchmark harness and Faster-Whisper baseline first. Then perform a disposable
Moonshine packaging spike and compare Tiny Streaming, Base, and Small Streaming on the same
labeled corpus. Do not modify the production default until the decision-confusion matrix,
target-host p95 latency, and RSS results are reviewed together.

