# Accelerator families (GPU family, Phase A6)

One image, per-family torch wheels. The baked image ships only the CPU torch
wheel; when a non-CPU accelerator family is detected, the entrypoint installs
that family's torch wheel on first boot into a persisted volume, so the same
image serves CPU, Intel iGPU, NVIDIA, and AMD hosts.

## Family vs. device (two independent axes)

- **Family** — which torch *wheel* to install. `GPU_FAMILY`
  (default `auto`) resolved by `persona_forge/gpu_family.py::resolve_gpu_family`.
  This is deliberately torch-independent: inside the CPU-base image,
  `torch.<accel>.is_available()` is always False even with a GPU passed
  through (the CPU wheel has no accel support compiled in), so family
  selection must never depend on torch. Probes are pure filesystem reads:
  - PCI vendor IDs from `/sys/bus/pci/devices/*/vendor` — NVIDIA `0x10de`,
    AMD `0x1002`, Intel `0x8086`.
  - Device nodes: `/dev/nvidia*` (cuda), `/dev/kfd` (rocm — AMD-exclusive),
    `/dev/dri/renderD*` (intel-xpu).
- **Device** — where a torch-backed model loads *at runtime*. `TTS_DEVICE`
  (legacy alias `DEVICE`) resolved by `persona_forge/device.py::resolve_device`:
  auto-detect `cuda` > `xpu` > `mps` > `cpu`, or a forced value. A
  forced-but-unavailable device warns and falls back to `cpu` rather than
  failing. `OPENVINO_DEVICE` (`CPU`/`GPU`/`AUTO`) is a third, separate axis —
  the OpenVINO compile target for the Qwen3-TTS cores only.

Family resolution rules:

- `auto` picks the highest-priority vendor (`cuda` > `rocm` > `intel-xpu`)
  only when the device node is actually present ("capable"). A PCI-presence
  match without the mapped device node stays `cpu` until the hardware is
  actually passed through.
- An explicit `GPU_FAMILY=<family>` (including `cpu`) always wins.
- An unrecognized value warns and falls back to auto-detect.

The distinction Pocket-TTS vs. Qwen: the family axis changes the torch wheel
used by the Qwen3-TTS PyTorch backend and OmniVoice (both torch models).
Pocket-TTS is CPU-only and is unaffected by family selection.

## Entrypoint behavior (Phase A6d / A6e)

`scripts/entrypoint.sh`, before exec-ing the CMD:

1. Resolves the family with `resolve_gpu_family()` and logs it (A6d).
2. If the family is not `cpu` (A6e): when the marker file
   `${ACCEL_VENV_DIR}/<family>/.installed` (default `ACCEL_VENV_DIR` is
   `/opt/accel-venv`, a named compose volume) is missing, it installs once
   into `${ACCEL_VENV_DIR}/<family>/site-packages` via
   `pip install --target`:
   - `torch` + `torchaudio` from the family's wheel index — all families
     default to version `2.8.0`, overridable via `ACCEL_TORCH_INDEX_URL` and
     `ACCEL_TORCH_VERSION`:
     - `intel-xpu` → `https://download.pytorch.org/whl/xpu`
     - `cuda` → `https://download.pytorch.org/whl/cu124`
     - `rocm` → `https://download.pytorch.org/whl/rocm6.2`
   - the pinned `omnivoice` (same pin as the Dockerfile).
   The site-packages directory is then prepended to `PYTHONPATH`. The marker
   is written only after a successful install (and `set -e` exits on
   failure), so a failed install can never look done.
3. If the family is `intel-xpu` (A6a): exports the NEO fp64
   software-emulation env vars (`NEOReadDebugKeys`, `OverrideDefaultFP64Settings`,
   `IGC_EnableDPEmulation`) plus `OPENVINO_DEVICE=GPU`. All use `${VAR:-default}`
   so an operator-set value is never clobbered. fp64 emulation is required on
   Xe-LP iGPUs (no native fp64) and harmless on Arc discrete (native fp64);
   it must be set before any xpu allocation — see
   `device.py::apply_fp64_emulation_env` for the in-Python equivalent.

## Image build (Phase A6f)

Dockerfile build arg `INSTALL_ACCEL_SYSLIBS` (default `0`). When set to `1`,
the image layers in the Intel iGPU userspace stack (`intel-opencl-icd`,
`libze1`, `libze-intel-gpu1`, `libigc2`, `libigdgmm12`) from Intel's official
GPU apt repo, so only the torch wheel varies per family at runtime. Left off,
the canonical CPU image stays byte-identical.

Debian-trixie compatibility of Intel's repo is **UNVALIDATED** (the repo
historically targets Ubuntu; Debian's own archive does not carry these
packages). Validate with a real build + generate check on Intel iGPU hardware
before relying on it.

## Validation status

- `intel-xpu`: **validated** on real Xe-LP iGPU hardware (host `plexxie`, per
  A6.1) — fp64-emu env + torch-xpu wheel + OmniVoice on the iGPU.
- `cuda` / `rocm`: index URLs and wheel versions are **unvalidated** on real
  hardware. Treat as best-effort; override `ACCEL_TORCH_INDEX_URL` /
  `ACCEL_TORCH_VERSION` as needed.

## Surface and tests

- `describe_accelerator()` (`gpu_family.py`) returns
  `{family, detected_family, device, has_fp64, emu_active, present, capable}`
  for health reporting / an accelerator status panel. `present` / `capable` /
  `detected_family` reflect the *actual detected* hardware (independent of any
  `GPU_FAMILY` override) — that split is what an "you have the hardware, map
  it" coach needs. `family` is the *resolved* family (override-aware) and can
  differ from `detected_family`. Unit-tested in
  `tests/tier1_unit/test_gpu_family.py` with injectable probes; not yet
  surfaced in `/health`.
- compose wires `GPU_FAMILY: ${GPU_FAMILY:-auto}` on the persona-forge service
  and mounts the `accel-venv` named volume at `/opt/accel-venv` (harmless/
  unused when the family resolves to `cpu`).

## Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `GPU_FAMILY` | `auto` | Torch wheel family: `cpu` / `intel-xpu` / `cuda` / `rocm` |
| `TTS_DEVICE` | auto-detect | Torch device for the Qwen3-TTS PyTorch backend and OmniVoice |
| `OPENVINO_DEVICE` | `AUTO` | OpenVINO compile target for the Qwen3-TTS cores (`CPU`/`GPU`) |
| `ACCEL_VENV_DIR` | `/opt/accel-venv` | Persisted per-family first-boot install location |
| `ACCEL_TORCH_INDEX_URL` | per-family (see above) | Wheel index for the first-boot torch install |
| `ACCEL_TORCH_VERSION` | `2.8.0` | torch/torchaudio version for the first-boot install |

Note: these accelerator vars are documented here rather than in
`ENV_REFERENCE.md` — add them there before treating the accelerator path as
an operator-facing knob.
