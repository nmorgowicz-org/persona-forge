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

exec "$@"
