# Gate 9D — Qwen/OpenVINO staged gates

Phase 9 of `docs/plans/20260829-no_more_docker_requirement.md`.

## Verdict: N/A — model execution unchanged on this branch

Gate 9D only requires the archived OpenVINO staged gates (baseline, FP32 tensor/token/cache
parity, quantized accuracy, listening, warm median/p95/RTF/RSS, PyTorch rollback) when this
branch changed model execution. It did not. This branch (`feat/no-docker-implementation`) is a
packaging/runtime/deployment change — cross-platform native `uv` setup, CLI, accelerator-family
torch install, path resolution, Docker/compose parity — not a change to how Qwen/OpenVINO
generates audio.

## Evidence

`git diff main...feat/no-docker-implementation --stat` shows exactly one file under
`src/persona_forge/openvino/` touched: `runtime_config.py`. The diff:

```diff
+from persona_forge import paths

 def get_ov_config() -> dict[str, object]:
     ...
-    cache_dir_raw = os.getenv("OV_CACHE_DIR", "/ov/cache").strip()
-    cache_dir = cache_dir_raw or None
+    resolved_cache_dir = paths.ov_cache_dir(os.environ)
+    cache_dir = str(resolved_cache_dir) if resolved_cache_dir is not None else None
```

This swaps a hardcoded `/ov/cache` default for the new cross-platform `persona_forge.paths`
resolver. Containerized behavior is explicitly unchanged: `docker-compose.yml` and the
Dockerfile both still set `OV_CACHE_DIR=/ov/cache` directly, so the resolved value inside a
container is identical before and after. No other line in `runtime_config.py`, and no line in
any other OpenVINO/Qwen source file (export pipeline, IR generation, quantization, inference,
tensor/token/cache handling), changed on this branch.

No IR was re-exported, no model weights changed, no inference code path changed. Re-running the
full staged-gate suite (baseline/parity/quantized-accuracy/listening/perf/rollback) would only
reconfirm numbers already recorded in the prior gates this plan's history references — not
required by the plan's own N/A escape hatch, and not repeated here.

## Fields (per the plan's hardware receipt schema)

All marked N/A — model execution unchanged, evidenced above:

- Baseline: N/A
- FP32 tensor/token/cache parity: N/A
- Quantized accuracy: N/A
- Listening: N/A
- Warm median/p95/RTF/RSS: N/A
- PyTorch rollback: N/A
- Model revision / IR metadata hash / capacity / compression / cache mode / prompt / seed /
  non-Git artifacts: N/A (no export or model-execution change to characterize)
