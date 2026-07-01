#!/usr/bin/env bash
# Container entrypoint. Applies LOW_RAM_MODE tuning before handing off to the
# gunicorn CMD (or the export command override from the compose export service).
set -e

if [ "${LOW_RAM_MODE:-0}" = "1" ]; then
    _JEMALLOC="/usr/lib/x86_64-linux-gnu/libjemalloc.so.2"
    if [ -f "$_JEMALLOC" ]; then
        export LD_PRELOAD="${LD_PRELOAD:-$_JEMALLOC}"
        # background_thread purges unused pages back to the OS continuously.
        # 1 s decay is aggressive but appropriate for a memory-constrained host.
        export MALLOC_CONF="${MALLOC_CONF:-background_thread:true,dirty_decay_ms:1000,muzzy_decay_ms:1000}"
        echo "[entrypoint] LOW_RAM_MODE: jemalloc loaded (${LD_PRELOAD}), MALLOC_CONF=${MALLOC_CONF}"
    else
        echo "[entrypoint] LOW_RAM_MODE: WARNING jemalloc not found at ${_JEMALLOC}, falling back to glibc"
    fi
    # Default idle unload to 30 min if the user has not set it explicitly.
    export IDLE_UNLOAD_SECONDS="${IDLE_UNLOAD_SECONDS:-1800}"
    echo "[entrypoint] LOW_RAM_MODE: idle unload after ${IDLE_UNLOAD_SECONDS}s"
fi

exec "$@"
