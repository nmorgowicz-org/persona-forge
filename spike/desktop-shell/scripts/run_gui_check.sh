#!/usr/bin/env bash
# Run inside `dbus-run-session -- xvfb-run -a` (spike 1C task 5).
# usage: run_gui_check.sh <full|ask> <appimage> <app-stderr-log> <download-dir>
# Starts tauri-driver (its stderr, which carries the app's [nav]/[download] lines, goes to the
# log), waits for it, runs gui_check.py, and always stops the driver and any app it launched.
# The app inherits its environment through tauri-driver -> WebKitWebDriver:
#   full: SPIKE_DOWNLOAD_DIR=<download-dir> (downloads saved there, no dialog)
#   ask:  SPIKE_ASK_WHERE_TO_SAVE=1 (download to temp, then a non-blocking Save dialog)
set -uo pipefail
MODE="$1"
APP="$2"
LOG="$3"
DL_DIR="$4"
HERE="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$DL_DIR"
case "$MODE" in
  full) export SPIKE_DOWNLOAD_DIR="$DL_DIR" ;;
  ask) export SPIKE_ASK_WHERE_TO_SAVE=1 ;;
  *) echo "unknown mode: $MODE" >&2; exit 2 ;;
esac

tauri-driver --port 4444 2>"$LOG" &
DRV=$!
# WebKitWebDriver can leave the app running after a session ends; stop both on exit.
# -x matches the process name exactly: -f would also match xvfb-run/uv, whose arguments
# contain the AppImage path, and kill our own parents.
trap 'kill "$DRV" 2>/dev/null || true; pkill -x desktop-spike 2>/dev/null || true' EXIT

for _ in $(seq 1 40); do
  curl -s -o /dev/null http://127.0.0.1:4444/status && break
  sleep 0.5
done

uv run --with selenium python "$HERE/gui_check.py" "$MODE" "$APP" "$LOG" "$DL_DIR"
