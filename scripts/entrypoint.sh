#!/usr/bin/env bash
# Container entrypoint. Applies LOW_RAM_MODE tuning before handing off to the
# gunicorn CMD (or the export command override from the compose export service).
set -e

if [ "${LOW_RAM_MODE:-0}" = "1" ]; then
    # Tune glibc malloc without replacing it via LD_PRELOAD.
    # Both jemalloc and tcmalloc caused free(): invalid size + SIGABRT/SIGSEGV
    # during OpenVINO compile_model() under transformers 5.x — OV's native C++
    # allocator conflicts with any LD_PRELOAD replacement.
    #
    # MALLOC_MMAP_THRESHOLD_: allocations larger than this use mmap and are
    # returned to the OS immediately on free() rather than pooled in arenas.
    # 64 KiB catches most of the large model tensor allocations.
    export MALLOC_MMAP_THRESHOLD_="${MALLOC_MMAP_THRESHOLD_:-65536}"
    # MALLOC_ARENA_MAX: cap the number of per-thread arenas to prevent glibc
    # from hoarding freed pages across many arenas.
    export MALLOC_ARENA_MAX="${MALLOC_ARENA_MAX:-1}"
    echo "[entrypoint] LOW_RAM_MODE: glibc tuning MALLOC_MMAP_THRESHOLD_=${MALLOC_MMAP_THRESHOLD_} MALLOC_ARENA_MAX=${MALLOC_ARENA_MAX}"
    # Default idle unload to 30 min; Python code calls malloc_trim(0) after unload.
    export IDLE_UNLOAD_SECONDS="${IDLE_UNLOAD_SECONDS:-1800}"
    echo "[entrypoint] LOW_RAM_MODE: idle unload after ${IDLE_UNLOAD_SECONDS}s"
fi

if [ -d "/app/.git" ]; then
    git config --global --add safe.directory /app || true
fi

# Phase A6d: resolve the accelerator family (torch-independent, see persona_forge/gpu_family.py)
# and export the per-family runtime env before handing off. Assumes the correct torch wheel is
# already present (installing it on demand is Phase A6e) — this step only sets env vars.
_gpu_family="$(python -c 'from persona_forge.gpu_family import resolve_gpu_family; print(resolve_gpu_family())' 2>/dev/null || echo cpu)"
echo "[entrypoint] accelerator family resolved: ${_gpu_family}"

# Phase A6e: first-boot per-family torch install into a persisted volume. The baked image only
# ships CPU torch; accel families install their wheel here, once, into $ACCEL_VENV_DIR so it
# survives container recreation. A missing marker means "never installed" — install fails ==
# script exits (set -e) before the marker is written, so a failed install can never look done.
_accel_venv_dir="${ACCEL_VENV_DIR:-/opt/accel-venv}"
if [ "${_gpu_family}" != "cpu" ]; then
    _accel_site_packages="${_accel_venv_dir}/${_gpu_family}/site-packages"
    _accel_marker="${_accel_venv_dir}/${_gpu_family}/.installed"

    if [ ! -f "${_accel_marker}" ]; then
        echo "[entrypoint] ${_gpu_family}: no cached torch install found at ${_accel_site_packages}, installing..."
        mkdir -p "${_accel_site_packages}"

        case "${_gpu_family}" in
            intel-xpu)
                _torch_index_url="${ACCEL_TORCH_INDEX_URL:-https://download.pytorch.org/whl/xpu}"
                _torch_version="${ACCEL_TORCH_VERSION:-2.8.0}"
                ;;
            cuda)
                _torch_index_url="${ACCEL_TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu124}"
                _torch_version="${ACCEL_TORCH_VERSION:-2.8.0}"
                ;;
            rocm)
                _torch_index_url="${ACCEL_TORCH_INDEX_URL:-https://download.pytorch.org/whl/rocm6.2}"
                _torch_version="${ACCEL_TORCH_VERSION:-2.8.0}"
                ;;
            *)
                echo "[entrypoint] ERROR: no torch install recipe for family '${_gpu_family}'" >&2
                exit 1
                ;;
        esac

        # cuda/rocm index URLs + versions are unvalidated on real hardware (only intel-xpu has been
        # proven, on plexxie, per A6.1); override via ACCEL_TORCH_INDEX_URL/ACCEL_TORCH_VERSION if wrong.
        pip install --target "${_accel_site_packages}" --no-cache-dir \
            "torch==${_torch_version}" "torchaudio==${_torch_version}" \
            --index-url "${_torch_index_url}"
        pip install --target "${_accel_site_packages}" --no-cache-dir --no-deps \
            "omnivoice @ git+https://github.com/k2-fsa/OmniVoice.git@${ACCEL_OMNIVOICE_REV:-398b6113}"

        touch "${_accel_marker}"
        echo "[entrypoint] ${_gpu_family}: install complete, marker written at ${_accel_marker}"
    else
        echo "[entrypoint] ${_gpu_family}: cached torch install found, skipping install"
    fi

    export PYTHONPATH="${_accel_site_packages}:${PYTHONPATH:-}"
fi

if [ "${_gpu_family}" = "intel-xpu" ]; then
    # NEO fp64 software-emulation vars (Phase A6a) — required for Xe-LP iGPUs, harmless
    # elsewhere; `${VAR:-1}` never clobbers an operator-set value.
    export NEOReadDebugKeys="${NEOReadDebugKeys:-1}"
    export OverrideDefaultFP64Settings="${OverrideDefaultFP64Settings:-1}"
    export IGC_EnableDPEmulation="${IGC_EnableDPEmulation:-1}"
    export OPENVINO_DEVICE="${OPENVINO_DEVICE:-GPU}"
    echo "[entrypoint] intel-xpu family: fp64-emu env set, OPENVINO_DEVICE=${OPENVINO_DEVICE}"
fi

exec "$@"
