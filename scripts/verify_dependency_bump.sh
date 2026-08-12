#!/usr/bin/env bash
# Locally verify a dependency-bump PR (Renovate/Dependabot) against real
# Torch-backed code paths that fast CI fakes out via FakeModelRuntime.
#
# Runs the same requires_torch pytest tier on both the PR branch and the
# base branch (default: main) so pre-existing flaky failures don't get
# blamed on the bump, then diffs the two result sets.
#
# Usage: scripts/verify_dependency_bump.sh <pr-number> [base-ref]
set -euo pipefail

PR="${1:?usage: verify_dependency_bump.sh <pr-number> [base-ref]}"
BASE_REF="${2:-main}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRATCH="$(mktemp -d)"
MARKER='requires_torch and not requires_model_weights and not requires_openvino_ir'

cleanup() {
  git -C "$ROOT" worktree remove "$SCRATCH/pr" --force 2>/dev/null || true
  git -C "$ROOT" worktree remove "$SCRATCH/base" --force 2>/dev/null || true
  rm -rf "$SCRATCH"
}
trap cleanup EXIT

run_tier() {
  local worktree_dir="$1"
  ( cd "$worktree_dir" \
    && uv sync --quiet \
    && PYTHONPATH=src:src/export uv run python -m pytest \
         -m "$MARKER" -q --tb=line 2>&1 )
}

echo "== Fetching PR #$PR and base ($BASE_REF) =="
git -C "$ROOT" fetch origin "pull/$PR/head" "$BASE_REF"
git -C "$ROOT" worktree add "$SCRATCH/pr" FETCH_HEAD >/dev/null
git -C "$ROOT" worktree add "$SCRATCH/base" "origin/$BASE_REF" >/dev/null

echo "== Running requires_torch tier on PR #$PR =="
pr_output="$(run_tier "$SCRATCH/pr")" || true
echo "$pr_output" | tail -5

echo "== Running requires_torch tier on $BASE_REF (baseline) =="
base_output="$(run_tier "$SCRATCH/base")" || true
echo "$base_output" | tail -5

pr_failed="$(echo "$pr_output" | grep -oE '^FAILED .*' | sort)"
base_failed="$(echo "$base_output" | grep -oE '^FAILED .*' | sort)"

new_failures="$(comm -23 <(echo "$pr_failed") <(echo "$base_failed"))"

echo
if [ -z "$new_failures" ]; then
  echo "PASS: no new failures vs $BASE_REF baseline."
  [ -n "$pr_failed" ] && echo "(pre-existing failures on both, unrelated to this bump: $pr_failed)"
  exit 0
else
  echo "FAIL: new failures introduced by PR #$PR:"
  echo "$new_failures"
  exit 1
fi
