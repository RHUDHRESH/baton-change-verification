#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
docker compose --profile checks build checks
docker compose --profile checks run --rm checks
