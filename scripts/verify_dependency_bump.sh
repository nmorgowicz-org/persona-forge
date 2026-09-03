#!/usr/bin/env bash
# Locally verify a dependency-bump PR (Renovate/Dependabot) against the source
# dependency contract and real Torch-backed code paths that fast CI fakes out.
#
# Checks that Dockerfile, pyproject.toml, uv overrides, and uv.lock agree before
# installing anything. Then it runs the same requires_torch pytest tier on both
# branches so pre-existing failures do not get blamed on the bump.
#
# Usage: scripts/verify_dependency_bump.sh <pr-number> [base-ref]
set -euo pipefail

PR="${1:?usage: verify_dependency_bump.sh <pr-number> [base-ref]}"
BASE_REF="${2:-main}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRATCH="$(mktemp -d)"
MARKER='requires_torch and not requires_model_weights and not requires_openvino_ir'
CHECKER="$ROOT/scripts/check_torch_stack.py"
export UV_CACHE_DIR="$SCRATCH/uv-cache"

cleanup() {
  git -C "$ROOT" worktree remove "$SCRATCH/pr" --force 2>/dev/null || true
  git -C "$ROOT" worktree remove "$SCRATCH/base" --force 2>/dev/null || true
  rm -rf "$SCRATCH"
}
trap cleanup EXIT

run_tier() {
  local worktree_dir="$1"
  (
    cd "$worktree_dir"
    uv lock --check
    uv sync --locked --extra qwen-tts
    PYTHONPATH=src:src/export uv run --frozen python -c \
      'import torch, torchaudio, transformers; print(f"torch={torch.__version__} torchaudio={torchaudio.__version__} transformers={transformers.__version__}")'
    PYTHONPATH=src:src/export uv run --frozen python -m pytest \
      -m "$MARKER" -q --tb=line
  )
}

run_and_capture() {
  local output_file="$1"
  shift
  set +e
  "$@" >"$output_file" 2>&1
  local status=$?
  set -e
  return "$status"
}

echo "== Fetching PR #$PR and base ($BASE_REF) =="
git -C "$ROOT" fetch origin "pull/$PR/head"
PR_SHA="$(git -C "$ROOT" rev-parse FETCH_HEAD)"
git -C "$ROOT" fetch origin "$BASE_REF"
git -C "$ROOT" worktree add "$SCRATCH/pr" "$PR_SHA" >/dev/null
git -C "$ROOT" worktree add "$SCRATCH/base" "origin/$BASE_REF" >/dev/null

echo "== Checking dependency declarations on PR #$PR =="
python "$CHECKER" --root "$SCRATCH/pr"

echo "== Checking dependency declarations on $BASE_REF =="
python "$CHECKER" --root "$SCRATCH/base"

echo "== Running requires_torch tier on PR #$PR =="
PR_LOG="$SCRATCH/pr-requires-torch.log"
if ! run_and_capture "$PR_LOG" run_tier "$SCRATCH/pr"; then
  echo "FAIL: PR #$PR dependency/test lane failed; full log: $PR_LOG" >&2
  cat "$PR_LOG" >&2
  exit 1
fi

echo "== Running requires_torch tier on $BASE_REF baseline =="
BASE_LOG="$SCRATCH/base-requires-torch.log"
if ! run_and_capture "$BASE_LOG" run_tier "$SCRATCH/base"; then
  echo "FAIL: $BASE_REF baseline dependency/test lane failed; full log: $BASE_LOG" >&2
  cat "$BASE_LOG" >&2
  exit 1
fi

pr_failed="$(awk '/^FAILED /' "$PR_LOG" | sort)"
base_failed="$(awk '/^FAILED /' "$BASE_LOG" | sort)"
new_failures="$(comm -23 <(printf '%s\n' "$pr_failed") <(printf '%s\n' "$base_failed"))"

echo
if [ -z "$new_failures" ]; then
  echo "PASS: no new failures vs $BASE_REF baseline."
  if [ -n "$pr_failed" ]; then
    echo "Pre-existing failures on both, unrelated to this bump:"
    printf '%s\n' "$pr_failed"
  fi
  exit 0
else
  echo "FAIL: new failures introduced by PR #$PR:"
  echo "$new_failures"
  echo "PR log: $PR_LOG"
  echo "Base log: $BASE_LOG"
  exit 1
fi
