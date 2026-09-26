#!/usr/bin/env bash
# Run inside `dbus-run-session -- xvfb-run -a` (spike 1C task 5).
# usage: run_gui_check.sh <appimage> <app-stderr-log>
# Starts tauri-driver (its stderr, which carries the app's [nav]/[download] lines, goes to the
# log), waits for it, runs gui_check.py, and always stops the driver.
set -uo pipefail
APP="$1"
LOG="$2"
HERE="$(cd "$(dirname "$0")" && pwd)"

tauri-driver --port 4444 2>"$LOG" &
DRV=$!
trap 'kill "$DRV" 2>/dev/null || true' EXIT

for _ in $(seq 1 40); do
  curl -s -o /dev/null http://127.0.0.1:4444/status && break
  sleep 0.5
done

uv run --with selenium python "$HERE/gui_check.py" "$APP" "$LOG"
