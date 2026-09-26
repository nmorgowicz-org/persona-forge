#!/usr/bin/env bash
# Desktop bundle smoke test for macOS and Linux (execution plan Phase 4, Gate 4).
#
# Usage: smoke_desktop.sh <macos|linux> <binary-path> <smoke-json-out>
#
# Runs the bundled app binary in smoke mode against a fresh PERSONA_FORGE_HOME
# (exported by the caller), asserts the smoke JSON reports ok, then runs it with
# a bogus flag and asserts exit code 2 (args.rs rejects unknown flags with 2).
# Fails closed: prints the smoke JSON on every outcome, and never leaves a
# server behind (final `pgrep` must find no `persona_forge.app:app`).
set -euo pipefail

PLATFORM="${1:?Usage: smoke_desktop.sh <macos|linux> <binary-path> <smoke-json-out>}"
BINARY="${2:?Usage: smoke_desktop.sh <macos|linux> <binary-path> <smoke-json-out>}"
SMOKE_JSON="${3:?Usage: smoke_desktop.sh <macos|linux> <binary-path> <smoke-json-out>}"

case "$PLATFORM" in
  macos|linux) ;;
  *) echo "FAIL: unknown platform '$PLATFORM' (expected macos or linux)" >&2; exit 1 ;;
esac

if [ ! -x "$BINARY" ]; then
  echo "FAIL: binary is missing or not executable: $BINARY" >&2
  exit 1
fi

if [ -z "${PERSONA_FORGE_HOME:-}" ]; then
  echo "FAIL: PERSONA_FORGE_HOME must be exported to a fresh state dir before calling" >&2
  exit 1
fi

no_server_left_behind() {
  if pgrep -f 'persona_forge.app:app' >/dev/null 2>&1; then
    echo "FAIL: a persona_forge.app:app server process survived the smoke run" >&2
    exit 1
  fi
}
trap no_server_left_behind EXIT

echo "--- smoke run: --smoke-test $SMOKE_JSON"
if ! "$BINARY" --smoke-test "$SMOKE_JSON"; then
  echo "FAIL: --smoke-test exited non-zero; server/bootstrap logs:" >&2
  for LOG in \
    "$PERSONA_FORGE_HOME"/desktop/logs/*.log \
    "${TMPDIR:-/tmp}"/persona-forge-smoke-*.log; do
    if [ -f "$LOG" ]; then
      echo "===== $LOG =====" >&2
      tail -n 120 "$LOG" >&2
    fi
  done
  exit 1
fi

echo "--- smoke JSON:"
cat "$SMOKE_JSON"

python3 - "$SMOKE_JSON" <<'PY'
import json, sys

with open(sys.argv[1], "rb") as f:
    report = json.load(f)
if report.get("ok") is not True:
    print(f"FAIL: smoke report did not report ok: {json.dumps(report)}", file=sys.stderr)
    sys.exit(1)
print("smoke report ok")
PY

echo "--- smoke run: --bogus (must exit 2)"
set +e
"$BINARY" --bogus
STATUS=$?
set -e
if [ "$STATUS" -ne 2 ]; then
  echo "FAIL: --bogus exited with $STATUS, expected 2" >&2
  exit 1
fi

echo "PASS: smoke ($PLATFORM)"
