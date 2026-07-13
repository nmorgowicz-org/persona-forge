# Prosody alignment hardening

Phase 5 turns the plan's five-second PRECISE latency target into an observable, repeatable
gate. The portable `CPUExecutionProvider` remains the baseline; optional providers must pass
the same command before they are recommended.

## Runtime contract

- Alignment jobs remain serialized and cancellable.
- Every started job reports `started_at`, `finished_at`, `duration_seconds`,
  `latency_budget_seconds`, and `within_latency_budget`.
- `GET /alignment/performance` exposes a bounded 100-job window with p50, p95, breach count,
  and the configured budget. `GET /health` includes the same record. This operational window
  intentionally includes cold starts and cache hits; the standalone benchmark below is the
  authoritative warm-p95 release gate.
- A slow successful alignment is not discarded: the Voice Library keeps the usable result
  and shows an explicit latency-budget warning. Alignment failure still uses the existing
  VAD-safe fallback.
- Invalid/non-positive budget or idle-unload environment values fail safe to their defaults.

## Generation output repair contract

- Complete-file routes (`/generate`, `/generate/with_metrics`, `/v1/audio/speech`, and
  `/generate/async`) accept only an explicit boolean `prosody_repair`; omission is a strict
  no-op and never invokes triage or alignment.
- Repair reuses `prosody_repair.repair_segment_audio`, including the canonical resolved
  boundary plan and renderer used by Voice Library, Stitch Studio, and OmniVoice.
- `GENERATION_REPAIR_BUDGET_SECONDS` defaults to 5 seconds. The request returns the original
  pre-repair waveform on deadline or failure. A late ONNX call may finish in its daemon
  worker because ONNX Runtime cannot interrupt `session.run`, but cancellation checks prevent
  the late result from being rendered or cached.
- Outcomes are `repaired`, `unnecessary`, `failed`, or `budget_fallback`; omitted requests
  report `not_requested`. Raw audio routes expose `X-Prosody-Repair-*` headers, while metrics
  and async progress expose the same record as JSON.
- Streaming rejects `prosody_repair: true`: already-emitted PCM cannot be repaired safely.

### Validated generation result (2026-07-13)

- Runtime: `dockermisc1`, Pocket TTS, `qwen3-tts-openvino:local`, development bind mounts,
  source candidate `88d0149`.
- Input: `The rain stopped suddenly. Everyone stepped outside to listen. Then the city
  began to breathe again.` with seed `424242`, WAV output, and ordinary postprocessing off.
- Unflagged control: HTTP 200, `not_requested`, SHA-256
  `6a1423df520946cc613c3fdd8ae021d99f98a57368f83039c2c659a2320e0bbe`.
- Cold flagged request: HTTP 200, `budget_fallback` at `5.000339 s` against the `5.0 s`
  deadline, with the exact same byte hash as the control.
- Warm native and OpenAI-compatible requests: HTTP 200 with `unnecessary` because triage
  found adequate natural gaps; repair decision time was `0.011341 s` and `0.004914 s`.
- Async request: pending metadata at submission, then completed audio plus structured
  `unnecessary` progress and matching download headers (`0.009405 s`).
- Container logs showed no late-worker, alignment, renderer, or generation errors.

## Target-CPU benchmark gate

Keep benchmark audio outside Git and use its exact transcript:

```bash
PYTHONPATH=src .venv/bin/python scripts/benchmark_aligner.py \
  --audio /path/to/reference.wav \
  --transcript-file /path/to/reference.txt \
  --iterations 10 \
  --warmup 1 \
  --budget-seconds 5
```

The command unloads the session, records one cold pass, then measures warm p50/p95. It exits
non-zero when warm p95 is greater than or equal to the budget. Output contains timing,
provider, immutable model revision, CPU count, audio duration, boundary count, and peak
process RSS; it never contains audio or transcript text.

## Dev-container verification

On `dockermisc1`, update only the qwen project and recreate only its development service:

```bash
cd ~/projects/qwen3-tts-openvino
git pull
cd frontend
npm run build
cd ~/docker
docker compose -f docker-compose.yml -f docker-compose.qwen3-tts-dev.yml \
  up -d --force-recreate qwen3-tts
```

Verify `/health`, run a Precise alignment against a representative saved reference, poll the
job to completion, inspect `/alignment/performance`, and run the benchmark above inside the
same image/bind-mounted source environment. Record host CPU, available RAM/swap, provider,
audio duration, cold time, warm p50/p95, and peak RSS.

Rollback is `git revert <phase-5-commit>` followed by the same frontend build and service
recreate. No model, IR, or audio artifact is changed by Phase 5.

## Validated target result (2026-07-13)

- Host: `dockermisc1`, Intel Core i7-1360P, 8 CPU threads allocated to the environment.
- Runtime: development Compose bind mounts, `qwen3-tts-openvino:local`, Pocket TTS loaded;
  forced aligner on `CPUExecutionProvider`.
- Aligner: `mms-onnx-v1`, model revision
  `2100fb247d8e43962eef24491597fbeb8b469531`.
- Input: the 11.16-second Aussie screenshot reference already used by the plan, with its
  exact stored transcript. Audio and transcript artifacts remained outside Git.
- Result (10 measured warm iterations after one warmup): cold session load `5.106 s`, warm
  p50 `3.511 s`, warm p95 `4.136 s`, peak benchmark process RSS `958.4 MiB` — **pass**
  against the strict `< 5 s` gate.
- Host snapshot after the run: load average `4.66 / 2.25 / 1.40`; 15,382 MiB RAM total,
  6,598 MiB available; 16,383 MiB swap total, 6,589 MiB used. Serving container settled at
  about `963.8 MiB` during the snapshot.
- The first live forced-alignment API job included initial provisioning/session load and took
  `11.478 s`; it completed successfully, marked `within_latency_budget=false`, appeared in
  `/alignment/performance`, and retained its usable alignment result as designed.
