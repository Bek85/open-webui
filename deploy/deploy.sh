#!/usr/bin/env bash
# Deploy the latest custom/main on this server.
#
# Replaces the old "bump BUILD_HASH + commit + rebuild" dance: develop on your machine,
# push to custom/main, then just run this here. It builds the open-webui image from the
# local checkout (no GitHub clone, no SHA pin) and restarts the stack.
set -euo pipefail

cd "$(dirname "$0")/.."                       # custom/main checkout root = build context

echo "→ pulling latest custom/main…"
git pull --ff-only

OWUI_VERSION="$(git rev-parse --short HEAD)"
export OWUI_VERSION
echo "→ building + deploying open-webui @ ${OWUI_VERSION}…"
docker compose -f deploy/docker-compose.yml up -d --build

echo "✓ open-webui @ ${OWUI_VERSION} is live"
