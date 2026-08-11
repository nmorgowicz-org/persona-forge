#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
npm --prefix frontend run build
cd ~/docker
docker compose -f docker-compose.yml -f docker-compose.persona-forge-dev.yml \
  up -d persona-forge --force-recreate
