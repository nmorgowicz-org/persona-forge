#!/usr/bin/env bash
# Container entrypoint. Applies LOW_RAM_MODE tuning before handing off to the
# gunicorn CMD (or the export command override from the compose export service).
set -e

if [ "${LOW_RAM_MODE:-0}" = "1" ]; then
    # Default idle unload to 30 min if the user has not set it explicitly.
    # Jemalloc LD_PRELOAD was removed: it conflicts with OpenVINO's native
    # allocator under transformers 5.x, causing free(): invalid size + SIGABRT.
    export IDLE_UNLOAD_SECONDS="${IDLE_UNLOAD_SECONDS:-1800}"
    echo "[entrypoint] LOW_RAM_MODE: idle unload after ${IDLE_UNLOAD_SECONDS}s"
fi

exec "$@"
