# Local development setup (uv)

This doc covers running the backend **directly on your machine** (not in the Docker container) for
fast iteration — writing/debugging Python, running the real-model capture harness, etc. The
container build (`Dockerfile`) is the canonical, production-facing path and is **not** migrated to
`uv`; this is a local-dev convenience layered on top (see `pyproject.toml` / `uv.lock`).

Just want to *run* Persona Forge natively rather than develop against it (no repo checkout, or
you don't need the dev/test tooling below)? See [../RUN_LOCAL.md](../RUN_LOCAL.md) instead — it
covers the same `uv sync` path plus the installed-wheel and launcher-archive alternatives, with
none of the iteration-focused detail below.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) installed (`brew install uv` on macOS).
- Python 3.13 (uv will fetch/select it automatically per `pyproject.toml`'s
  `requires-python = ">=3.13,<3.14"`).
- `ffmpeg` as a system binary: `brew install ffmpeg` (needed by the real-model capture harness,
  Initiative B; ships via `apt-get` in the container).
- `sox` as a system binary: `brew install sox` (used by `pydub`/audio conversion paths; also an
  `apt-get` package in the container). Its absence doesn't crash imports, but audio operations that
  shell out to it will fail.

## Fast path — dev/test only (no real model)

```bash
uv sync --group dev
PYTHONPATH=src:. uv run pytest tests/ -q
```

This installs only the light CI-equivalent set (`requirements-dev.txt`'s contents, mirrored in the
`dev` dependency group) — no torch, no transformers, no gunicorn. Good enough for the fake-model
test tiers and most unit tests.

## Full path — real model locally

```bash
uv sync
```

`uv sync` (no `--group`/`--extra` filter) pulls Persona Forge's main runtime set: `gunicorn`,
`torch`, `transformers`, `omnivoice`, `pocket-tts`, etc., resolved universally for macOS (arm64,
cpu+mps) and Linux (cpu+cuda-auto) via an `override-dependencies` pin — see `pyproject.toml` for
the rationale (OmniVoice's git source declares a `cu128` index that the override strips).
Qwen3-TTS (`qwen-tts`) is an opt-in engine, not installed by a bare `uv sync` — add it with:

```bash
uv sync --extra qwen-tts
uv run python scripts/patch_local_compat.py   # one-time per fresh venv, only needed for qwen-tts, see below
```

**`scripts/patch_local_compat.py` is required after every fresh `uv sync --extra qwen-tts`.**
`qwen-tts==0.1.1` was written against an older `transformers` API; both the Docker image and this
script apply the same patches (Phase 5's `src/persona_forge/compat_patch.py`) to bridge that gap
after install — one definition, two callers, so they can no longer drift apart. A plain
`uv sync --extra qwen-tts` doesn't apply those patches, so `from persona_forge.app import app` fails
without running this script once against the new `.venv`. It's genuinely idempotent — safe to
re-run — including against the rope-parameters insertion, which is marker-guarded rather than
re-applied on every run. Use `persona-forge setup --apply-qwen-patches` for the same effect via the
CLI (`persona-forge setup` alone only verifies patch status when `qwen_tts` is installed, and is a
no-op otherwise).

Set `HF_TOKEN` in your shell (not `.env` — that's for the container) if your selected checkpoint is
gated.

### Backend choice for local runs

The product default backend is `pocket_tts` (self-contained, no export step), set explicitly in
`.env.example` — it wins over `presets.py`'s own fallback (`config.py`'s explicit-wins rule).
`presets.py`'s `PRESETS` fallback is `pytorch`, not `pocket_tts`: those presets are Qwen3-TTS-specific
(`model_repo` points at a Qwen3-TTS checkpoint), which `pocket_tts` — a wholly separate engine — cannot
run; it can only ever be `pytorch` (cpu/cuda/mps/rocm/xpu) or `openvino`. OmniVoice + pocket-tts are
Persona Forge's main accent-design/cloning levers and are always installed by a plain `uv sync`.
Qwen3-TTS (`qwen-tts`, plus the `openvino`/`export` groups on top of it) is the opt-in engine —
install it with `uv sync --extra qwen-tts` (add `--group openvino` for the Intel-CPU-accelerated
path, which also requires an exported IR at `OV_MODEL_DIR/metadata.json` that doesn't exist on a
fresh checkout). If you invoke the Qwen3-TTS path directly (e.g. `MODEL_SIZE` set without an
explicit `TTS_BACKEND`), the fallback auto-selects: `openvino` if a valid IR export already exists
on disk for that preset, otherwise `pytorch` (works everywhere — `TTS_DEVICE` auto-detects
`cuda`/`xpu`/`mps`/`cpu`, so Apple Silicon uses `mps` with no extra setup). This never triggers the
export itself — running it is still a deliberate, separate step. `/health` reports
`backend_source`/`backend_fallback_choice` so you can see which mode was picked and why.

## Verifying your environment

```bash
uv run python -c "import gunicorn, torch, transformers; print(torch.__version__)"
uv run python -c "import torch; print('mps', torch.backends.mps.is_available())"   # macOS only
PYTHONPATH=src:src/export uv run python -c "from persona_forge.app import app; print('app import OK')"
```

## Native install & accelerators

A plain `uv sync` already covers most targets — no extras matrix needed (D9):

| Target | Command | Result |
|---|---|---|
| macOS (Apple Silicon) | `uv sync` | arm64 **cpu+mps**; runtime auto-detects `mps` (Phase A4) |
| linux + NVIDIA | `uv sync` | CUDA-enabled wheel; runtime auto-detects **cuda** (Phase A4) |
| linux CPU-only | `uv sync` | works, runs on **cpu** — but ~**5.5 GB** venv (unused NVIDIA libs pulled in by the CUDA wheel) |
| Intel iGPU | `uv sync --extra qwen-tts`, export once, `OPENVINO_DEVICE=GPU` | Qwen3-TTS on the iGPU; needs `intel-opencl-icd` + `intel-level-zero-gpu` + `/dev/dri` passthrough. The backend fallback auto-selects `openvino` once the export exists (Phase A4b) — no manual `TTS_BACKEND` needed after that. **OmniVoice also runs on the same iGPU** — separately, via `torch-xpu` + auto fp64-emulation (Phase A6, validated on real Xe-LP hardware), not via OpenVINO; see `GPU_FAMILY=intel-xpu` in `compose.yml` for the container path. |

Device selection is layered: `TTS_DEVICE` (or legacy `DEVICE`) forces a torch device if set,
otherwise auto-detects `cuda` > `xpu` > `mps` > `cpu`; a forced-but-unavailable device warns and
falls back to `cpu` rather than failing. `OPENVINO_DEVICE` (`CPU`/`GPU`/`AUTO`) is the separate
Qwen3-TTS-OpenVINO-only compile target for the Intel iGPU case above.

**Deferred / advanced — documented, not built:**
- **Slim CPU (no NVIDIA), ROCm, Intel XPU torch wheels.** Blocked by OmniVoice's cu128 git-source
  dominating `uv` resolution — validated: `UV_TORCH_BACKEND=cpu` still resolved `torch 2.11.0+cu128`
  on real linux. Reachable only by (a) pointing `[tool.uv.sources] omnivoice` at a fork/checkout with
  its `[tool.uv]` index block stripped (mirrors the container's pip `--no-deps`), then declaring
  torch from the desired index; or (b) an extras + `conflicts` + cu128-absorber setup. Both add real
  maintenance — defer until there's demand (e.g. a genuinely disk-constrained CPU LXC).
- **OmniVoice on OpenVINO / iGPU:** out of scope (D10) — a separate SD-pipeline-scale conversion.
  OmniVoice's Intel-iGPU path (validated, Phase A6) goes through `torch-xpu` instead.

## Relationship to the container build

The container (`Dockerfile`, `compose.yml`) remains the canonical, production path and is not
touched by this local-dev setup — it still installs from `requirements/*.txt` directly, not from
`pyproject.toml`/`uv.lock`. Keep both in sync by hand when the dependency set changes (see the
comment header in `pyproject.toml`).
