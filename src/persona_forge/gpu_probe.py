"""GPU validation probe (Phase 9 Task 4, contract D23).

Runs the same checks as ``scripts/gpu_validate.sh`` Task 0 but as an importable
module so the Rust launcher can invoke it after provisioning an accelerated
environment.  Prints JSON to stdout; exits 0 when the device works, 1 otherwise.

Usage::

    <venv-python> -m persona_forge.gpu_probe

Exit codes:
    0 — torch is installed and the device works (CUDA available + matmul passes)
    1 — torch missing, CUDA unavailable, or matmul failed
"""

from __future__ import annotations

import json
import sys

__all__ = ["run_probe", "main"]


def run_probe() -> dict:
    """Run the GPU validation probe and return the result as a dict.

    The dict contains:
    - ``torch_version``: str | None
    - ``cuda_version``: str | None
    - ``cuda_available``: bool
    - ``device_name``: str | None
    - ``compute_capability``: tuple[int, int] | None
    - ``arch_list``: list[str] | None
    - ``matmul_pass``: bool | None
    - ``error``: str | None (only when something went wrong)
    """
    result: dict = {
        "torch_version": None,
        "cuda_version": None,
        "cuda_available": False,
        "device_name": None,
        "compute_capability": None,
        "arch_list": None,
        "matmul_pass": None,
        "error": None,
    }

    try:
        import torch

        result["torch_version"] = torch.__version__
        result["cuda_version"] = getattr(torch.version, "cuda", None)

        if torch.cuda.is_available():
            result["cuda_available"] = True
            result["device_name"] = torch.cuda.get_device_name(0)
            result["compute_capability"] = tuple(
                torch.cuda.get_device_capability(0),
            )
            result["arch_list"] = torch.cuda.get_arch_list()

            # --- matmul test ---
            # 1024×1024 float32 matmul on device, compared against CPU.
            # rtol=1e-3, atol=1e-2 (Phase 9 fix for GPU float differences).
            size = 1024
            a = torch.randn(size, size, dtype=torch.float32, device="cuda")
            b = torch.randn(size, size, dtype=torch.float32, device="cuda")
            c_gpu = a @ b

            a_cpu = a.cpu()
            b_cpu = b.cpu()
            c_cpu = a_cpu @ b_cpu

            result["matmul_pass"] = bool(
                torch.allclose(c_gpu.cpu(), c_cpu, rtol=1e-3, atol=1e-2),
            )
        else:
            result["error"] = "CUDA not available"
    except ImportError:
        result["error"] = "torch is not installed"
    except Exception as e:
        result["error"] = f"probe failed: {e}"

    return result


def main() -> None:
    """Entry point for ``python -m persona_forge.gpu_probe``."""
    result = run_probe()
    print(json.dumps(result, indent=2))

    # Exit 0 only when torch is installed AND CUDA works AND matmul passes.
    ok = (
        result["error"] is None
        and result["cuda_available"]
        and result["matmul_pass"]
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
