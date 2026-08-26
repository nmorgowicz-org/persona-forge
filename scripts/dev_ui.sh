#!/usr/bin/env bash
# One-command local launch of the VoiceDesign frontend against the fake-model test server —
# no Docker, no real model weights, works on any dev machine/architecture (including an arm64
# Mac). See docs/archive/screenshots/E2E_AND_SCREENSHOTTING.md §3.1.
#
# Usage: scripts/dev_ui.sh [--rebuild] [port]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT=8319
REBUILD=0

for arg in "$@"; do
  case "$arg" in
    --rebuild) REBUILD=1 ;;
    *) PORT="$arg" ;;
  esac
done

if [ ! -d "${REPO_ROOT}/frontend/dist" ] || [ "$REBUILD" = "1" ]; then
  echo "[dev_ui] building frontend..."
  (cd "${REPO_ROOT}/frontend" && npm run build)
fi

echo "[dev_ui] starting fake-model server on http://127.0.0.1:${PORT}"
echo "[dev_ui] open that URL in a browser. Ctrl-C to stop."
exec node "${REPO_ROOT}/tests/ui/run-server.mjs" "${PORT}"
