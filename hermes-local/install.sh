#!/usr/bin/env bash
# One-shot installer: runs every step in order.
# Individual steps live in scripts/ and can be re-run independently.
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Hermes local deployment ==="
./scripts/00-preflight.sh
./scripts/01-install-deps.sh
./scripts/02-build-llama.sh
./scripts/03-fetch-model.sh
./scripts/04-install-service.sh
./scripts/05-smoke-test.sh
