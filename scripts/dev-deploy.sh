#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Usage: scripts/dev-deploy.sh [branch]  (defaults to main)
BRANCH="${1:-main}"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

npm --prefix frontend run build

# src/ and frontend/dist/ are bind-mounted into the dev container, so Python/JS source
# changes are picked up on container recreate alone. New/updated pip dependencies live in
# the image's site-packages though, so persona-forge:local must actually be rebuilt here.
docker build -t persona-forge:local .

cd ~/docker
docker compose -f docker-compose.yml -f docker-compose.persona-forge-dev.yml \
  up -d persona-forge --force-recreate
