#!/usr/bin/env bash
# Run the server in the foreground as the current user. Useful for a first
# try and for debugging before installing the systemd service. Ctrl-C stops it.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

model=$(model_path)
[ -n "$model" ] && [ -f "$model" ] || die "no model found - run 03-fetch-model.sh first"
[ -x "$HERMES_BIN_DIR/llama-server" ] || die "llama-server not built - run 02-build-llama.sh first"

args=(
  --model "$model"
  --host "$HERMES_HOST"
  --port "$HERMES_PORT"
  --ctx-size "$HERMES_CTX"
  --parallel "$HERMES_PARALLEL"
  --threads "$(resolve_threads)"
  --n-gpu-layers "$(resolve_ngl)"
  --alias hermes-4-14b
  --jinja
)
[ -n "$HERMES_API_KEY" ] && args+=(--api-key "$HERMES_API_KEY")

info "starting llama-server on ${HERMES_HOST}:${HERMES_PORT}"
info "model: $model"
info "threads=$(resolve_threads) gpu-layers=$(resolve_ngl) ctx=${HERMES_CTX}"
echo
exec "$HERMES_BIN_DIR/llama-server" "${args[@]}"
