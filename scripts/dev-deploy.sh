#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Deploy the working checkout to the dev container on docker-agent.
#
# Run this ON docker-agent, from /home/nick/projects/persona-forge.
#
# The dev override (docker-compose.persona-forge-dev.yml) bind-mounts src/ and
# frontend/dist/ over the pinned ghcr image, so the common case -- a frontend or
# Python change -- needs only a frontend build. Pass --image to rebuild the
# container image, which is required only when Python *dependencies* or the
# Dockerfile change, since those live in the image's site-packages.
#
# Usage:
#   scripts/dev-deploy.sh                 # build frontend from current branch, restart
#   scripts/dev-deploy.sh main            # switch to main first, then the above
#   scripts/dev-deploy.sh --image         # also rebuild persona-forge:local
#   scripts/dev-deploy.sh main --image
#   scripts/dev-deploy.sh --no-restart    # rebuild frontend only; static assets are
#                                         # served from the bind mount, so a browser
#                                         # refresh picks them up with no restart
#
# --no-restart depends on the dev override mounting frontend/ rather than
# frontend/dist/. `vite build` deletes and recreates dist/, and a bind mount of
# dist/ itself would keep pointing at the deleted inode and serve a stale build.

COMPOSE_DIR="${PERSONA_FORGE_COMPOSE_DIR:-$HOME/docker/docker-agent}"
BRANCH=""
BUILD_IMAGE=0
RESTART=1

for arg in "$@"; do
  case "$arg" in
    --image)      BUILD_IMAGE=1 ;;
    --no-restart) RESTART=0 ;;
    -*)           echo "unknown flag: $arg" >&2; exit 2 ;;
    *)            BRANCH="$arg" ;;
  esac
done

if [ -n "$BRANCH" ]; then
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
else
  echo "==> staying on $(git rev-parse --abbrev-ref HEAD) (pass a branch name to switch)"
fi

npm --prefix frontend run build

if [ "$BUILD_IMAGE" -eq 1 ]; then
  docker build -t persona-forge:local .
  echo "==> built persona-forge:local -- uncomment the image: line in"
  echo "    $COMPOSE_DIR/docker-compose.persona-forge-dev.yml to use it"
fi

if [ "$RESTART" -eq 0 ]; then
  echo "==> frontend rebuilt; skipping restart (refresh the browser)"
  exit 0
fi

cd "$COMPOSE_DIR"
docker compose -f docker-compose.yml -f docker-compose.persona-forge-dev.yml \
  up -d persona-forge --force-recreate
