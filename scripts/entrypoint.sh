#!/usr/bin/env bash
# Container entrypoint. Applies LOW_RAM_MODE tuning before handing off to the
# gunicorn CMD (or the export command override from the compose export service).
set -e

if [ "${LOW_RAM_MODE:-0}" = "1" ]; then
    # tcmalloc returns pages to the OS more aggressively than glibc malloc.
    # We use the minimal variant (no heap profiler) to reduce overhead.
    # Note: jemalloc was tried first but caused free(): invalid size + SIGABRT
    # during OpenVINO compilation under transformers 5.x (allocator mismatch).
    _TCMALLOC="/usr/lib/x86_64-linux-gnu/libtcmalloc_minimal.so.4"
    if [ -f "$_TCMALLOC" ]; then
        export LD_PRELOAD="${LD_PRELOAD:-$_TCMALLOC}"
        echo "[entrypoint] LOW_RAM_MODE: tcmalloc loaded (${LD_PRELOAD})"
    else
        echo "[entrypoint] LOW_RAM_MODE: WARNING tcmalloc not found at ${_TCMALLOC}, falling back to glibc"
    fi
    # Default idle unload to 30 min if the user has not set it explicitly.
    export IDLE_UNLOAD_SECONDS="${IDLE_UNLOAD_SECONDS:-1800}"
    echo "[entrypoint] LOW_RAM_MODE: idle unload after ${IDLE_UNLOAD_SECONDS}s"
fi

exec "$@"
