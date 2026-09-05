#!/usr/bin/env bash
# Download the Hermes GGUF weights into $HERMES_MODEL_DIR.
# Resumable: re-running after an interrupted download continues it.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

need_cmd python3

venv="$HERMES_PREFIX/venv"
if [ ! -x "$venv/bin/python" ]; then
  info "creating download venv at $venv"
  mkdir -p "$HERMES_PREFIX"
  python3 -m venv "$venv" || die "python3-venv missing; run 01-install-deps.sh first"
fi
info "ensuring huggingface_hub is installed"
"$venv/bin/pip" install --quiet --upgrade pip
"$venv/bin/pip" install --quiet "huggingface_hub>=0.24"

mkdir -p "$HERMES_MODEL_DIR"

info "fetching ${HERMES_MODEL_REPO} (${HERMES_QUANT}) into $HERMES_MODEL_DIR"
info "this is several GB and may take a while"

selected=$("$venv/bin/python" "$HERMES_ROOT/scripts/hf_fetch.py" \
  --repo "$HERMES_MODEL_REPO" \
  --quant "$HERMES_QUANT" \
  --dest "$HERMES_MODEL_DIR" \
  --file "$HERMES_MODEL_FILE") || die "model download failed (see error above)"

[ -n "$selected" ] || die "downloader did not report a filename"
echo "$selected" > "$HERMES_MODEL_DIR/.selected"

path="$HERMES_MODEL_DIR/$selected"
[ -f "$path" ] || die "expected model at $path but it is missing"

# GGUF files start with the magic bytes "GGUF"; catches truncated/HTML downloads.
magic=$(head -c 4 "$path")
[ "$magic" = "GGUF" ] || die "$path is not a valid GGUF file (bad magic: '$magic')"

size=$(du -h "$path" | cut -f1)
ok "model ready: $path ($size)"

if id -u "$HERMES_SERVICE_USER" >/dev/null 2>&1; then
  if [ "$(id -u)" -eq 0 ]; then
    chown -R "$HERMES_SERVICE_USER":"$HERMES_SERVICE_USER" "$HERMES_MODEL_DIR"
  else
    sudo chown -R "$HERMES_SERVICE_USER":"$HERMES_SERVICE_USER" "$HERMES_MODEL_DIR" 2>/dev/null \
      || warn "could not chown $HERMES_MODEL_DIR to $HERMES_SERVICE_USER; the service may not be able to read it"
  fi
fi

ok "continue with 04-install-service.sh (or run ./scripts/run-foreground.sh to try it first)"
