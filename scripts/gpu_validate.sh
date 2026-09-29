#!/usr/bin/env bash
# GPU validation probe (Phase 9 Task 0).
#
# Usage: bash scripts/gpu_validate.sh <extra> <python_version> <uv_version>
#
# Creates a Python venv, installs torch/torchaudio from the PyTorch index for
# the given extra, and runs a probe that prints JSON with torch/CUDA device
# info and a matmul test result.

set -euo pipefail

EXTRA="${1:?usage: gpu_validate.sh <extra> <python_version> <uv_version>}"
PYTHON_VERSION="${2:-3.13}"
UV_VERSION="${3:-0.12.9}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Map extra name to PyTorch index URL and torch/torchaudio versions.
# These match src/persona_forge/accelerator_manifest.py (single source of truth).
case "${EXTRA}" in
  cuda12)
    INDEX_URL="https://download.pytorch.org/whl/cu126"
    TORCH_VERSION="2.14.0"
    TORCHAUDIO_VERSION="2.11.0"
    ;;
  cuda13)
    INDEX_URL="https://download.pytorch.org/whl/cu130"
    TORCH_VERSION="2.14.0"
    TORCHAUDIO_VERSION="2.11.0"
    ;;
  xpu)
    INDEX_URL="https://download.pytorch.org/whl/xpu"
    TORCH_VERSION="2.13.0"
    TORCHAUDIO_VERSION="2.11.0"
    ;;
  *)
    echo "ERROR: unknown extra '${EXTRA}' (expected cuda12 | cuda13 | xpu)" >&2
    exit 1
    ;;
esac

echo "=== GPU Validation Probe ==="
echo "extra:        ${EXTRA}"
echo "index:        ${INDEX_URL}"
echo "torch:        ${TORCH_VERSION}"
echo "torchaudio:   ${TORCHAUDIO_VERSION}"
echo "python:       ${PYTHON_VERSION}"
echo "uv:           ${UV_VERSION}"
echo ""

WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT

# Install pinned uv.
curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh
export PATH="${HOME}/.local/bin:${PATH}"

# Create a fresh venv with the requested Python.
VENV_DIR="${WORKDIR}/venv"
uv venv --python "${PYTHON_VERSION}" "${VENV_DIR}"

if [[ -f "${VENV_DIR}/bin/activate" ]]; then
  source "${VENV_DIR}/bin/activate"
elif [[ -f "${VENV_DIR}/Scripts/activate" ]]; then
  source "${VENV_DIR}/Scripts/activate"
else
  echo "ERROR: activate script not found in ${VENV_DIR}" >&2
  exit 1
fi

# Install torch + torchaudio from the family's PyTorch index.
echo "Installing torch ${TORCH_VERSION} + torchaudio ${TORCHAUDIO_VERSION} from ${INDEX_URL} ..."
uv pip install \
  --index-url "${INDEX_URL}" \
  --index-strategy unsafe-best-match \
  "torch==${TORCH_VERSION}" \
  "torchaudio==${TORCHAUDIO_VERSION}"

echo ""
echo "=== Probe ==="

# Run the probe and capture its JSON output.
PROBE_OUTPUT="$(GPU_PROBE_EXTRA="${EXTRA}" python - <<'PY'
import json
import os
import sys

def probe():
    try:
        import torch
    except ImportError:
        return {"error": "torch not installed"}

    xpu = os.environ["GPU_PROBE_EXTRA"] == "xpu"
    backend = torch.xpu if xpu else torch.cuda
    available = backend.is_available()
    result = {
        "torch_version": torch.__version__,
        "torch_cuda_version": getattr(torch.version, "cuda", None),
        "cuda_available": torch.cuda.is_available(),
    }
    if xpu:
        result["xpu_available"] = available

    if available:
        result["device_name"] = backend.get_device_name(0)
        if not xpu:
            result["device_capability"] = torch.cuda.get_device_capability(0)
            result["arch_list"] = torch.cuda.get_arch_list()

        # Matmul test: 1024x1024 float32 on device vs CPU.
        try:
            N = 1024
            a_cpu = torch.randn(N, N, dtype=torch.float32)
            b_cpu = torch.randn(N, N, dtype=torch.float32)
            device = "xpu" if xpu else "cuda:0"
            a_gpu = a_cpu.to(device)
            b_gpu = b_cpu.to(device)

            result_gpu = a_gpu @ b_gpu
            result_cpu = a_cpu @ b_cpu

            match = torch.allclose(result_gpu.cpu(), result_cpu, rtol=1e-3, atol=1e-3)
            result["matmul_pass"] = bool(match)

            if not match:
                # Show the max difference for diagnostics.
                diff = (result_gpu.cpu() - result_cpu).abs().max().item()
                result["matmul_max_diff"] = diff
        except Exception as e:
            result["matmul_pass"] = False
            result["matmul_error"] = str(e)
    else:
        result["matmul_pass"] = None

    return result

print(json.dumps(probe(), indent=2))
PY
)"

echo "${PROBE_OUTPUT}"

# Exit non-zero if torch is installed but CUDA is unavailable (for cuda extras).
if [[ "${EXTRA}" == cuda12 || "${EXTRA}" == cuda13 ]]; then
    if echo "${PROBE_OUTPUT}" | python -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("cuda_available") else 1)'; then
        echo "PASS: CUDA available"
    else
        echo "FAIL: CUDA not available"
        exit 1
    fi
fi

if ! echo "${PROBE_OUTPUT}" | python -c '
import json, sys
result = json.load(sys.stdin)
extra = sys.argv[1]
available = result.get("xpu_available") if extra == "xpu" else result.get("cuda_available")
passed = available and (extra == "cuda12" or result.get("matmul_pass") is True)
if extra == "cuda13" and tuple(result.get("device_capability", ())) >= (12, 0):
    passed = passed and "sm_120" in result.get("arch_list", ())
sys.exit(0 if passed else 1)
' "${EXTRA}"; then
    echo "FAIL: ${EXTRA} GPU validation did not pass" >&2
    exit 1
fi

# For matmul test: warn if matmul failed (cuda12 on RTX 5090 is expected to fail).
if echo "${PROBE_OUTPUT}" | python -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("matmul_pass") is True else 1)'; then
    echo "PASS: matmul matches CPU"
else
    echo "NOTE: matmul did not match CPU (expected for cuda12 on newer GPUs)"
    echo "${PROBE_OUTPUT}" | python -c '
import json, sys
d = json.load(sys.stdin)
if d.get("matmul_error"):
    print("  matmul error: " + str(d["matmul_error"]))
if "matmul_max_diff" in d:
    print("  matmul max diff: " + str(d["matmul_max_diff"]))
'
fi
