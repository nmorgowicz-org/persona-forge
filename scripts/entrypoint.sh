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
    _accel_prefix="${_accel_venv_dir}/${_gpu_family}"
    _py_version="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    _accel_site_packages="${_accel_prefix}/lib/python${_py_version}/site-packages"
    _accel_marker="${_accel_prefix}/.installed"

    if [ ! -f "${_accel_marker}" ]; then
        echo "[entrypoint] ${_gpu_family}: no cached torch install found at ${_accel_site_packages}, installing..."
        mkdir -p "${_accel_site_packages}"

        # Defaults come from persona_forge.accelerator_manifest (Phase 4 Task 4/7) — the single
        # source of truth also validated against pyproject.toml's native uv extras — rather than
        # being hardcoded here a second time and drifting stale (the old cu124/rocm6.2/2.8.0
        # defaults this replaced went unnoticed for a full accelerator generation).
        _manifest_pin="$(python -c "
from persona_forge.accelerator_manifest import pin_for_family
p = pin_for_family('${_gpu_family}')
print(p.index_url if p else '')
print(p.torch_version if p else '')
print(p.torchaudio_version if p else '')
")"
        _manifest_index_url="$(echo "${_manifest_pin}" | sed -n '1p')"
        _manifest_torch_version="$(echo "${_manifest_pin}" | sed -n '2p')"
        _manifest_torchaudio_version="$(echo "${_manifest_pin}" | sed -n '3p')"
        if [ -z "${_manifest_index_url}" ]; then
            echo "[entrypoint] ERROR: no torch install recipe for family '${_gpu_family}'" >&2
            exit 1
        fi

        _torch_index_url="${ACCEL_TORCH_INDEX_URL:-${_manifest_index_url}}"
        _torch_version="${ACCEL_TORCH_VERSION:-${_manifest_torch_version}}"
        # ACCEL_TORCHAUDIO_VERSION is a new escape hatch (Task 6): when unset, fall back to the
        # old compatibility rule (torchaudio pinned to the same version as torch) only if
        # ACCEL_TORCH_VERSION was itself overridden (the operator is already deviating from the
        # manifest, so matching torchaudio to their torch choice is the safer guess); otherwise
        # use the manifest's own torchaudio pin, which need not equal the torch version.
        if [ -n "${ACCEL_TORCHAUDIO_VERSION:-}" ]; then
            _torchaudio_version="${ACCEL_TORCHAUDIO_VERSION}"
        elif [ -n "${ACCEL_TORCH_VERSION:-}" ]; then
            _torchaudio_version="${ACCEL_TORCH_VERSION}"
        else
            _torchaudio_version="${_manifest_torchaudio_version}"
        fi

        # index URL/version are unvalidated on real hardware for cuda/rocm (only intel-xpu has
        # been proven, on docker-agent, per Gate 9C); override via ACCEL_TORCH_INDEX_URL/
        # ACCEL_TORCH_VERSION/ACCEL_TORCHAUDIO_VERSION if wrong.
        #
        # --prefix, not --target: some accel wheels (e.g. intel-xpu's intel-sycl-rt) ship native
        # runtime libraries via install-scheme "data" entries with ../-relative RECORD paths,
        # meant to land at <prefix>/lib/*.so*. pip's --target mode has no destination for a path
        # that resolves outside site-packages and silently drops those files -- torch then
        # imports fine at install time but crashes at runtime with
        # "ImportError: libsycl.so.9: cannot open shared object file" (found on real Intel
        # iGPU hardware, Gate 9C). --prefix mode places them correctly.
        pip install --prefix "${_accel_prefix}" --no-cache-dir \
            "torch==${_torch_version}" "torchaudio==${_torchaudio_version}" \
            --index-url "${_torch_index_url}"
        pip install --prefix "${_accel_prefix}" --no-cache-dir --no-deps \
            "omnivoice==0.2.1"

        touch "${_accel_marker}"
        echo "[entrypoint] ${_gpu_family}: install complete, marker written at ${_accel_marker}"
    else
        echo "[entrypoint] ${_gpu_family}: cached torch install found, skipping install"
    fi

    export PYTHONPATH="${_accel_site_packages}:${PYTHONPATH:-}"
    # --prefix (see above) also places native runtime libraries under <prefix>/lib, which the
    # dynamic linker needs to find at import time (e.g. libsycl.so.9).
    export LD_LIBRARY_PATH="${_accel_prefix}/lib:${LD_LIBRARY_PATH:-}"
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
