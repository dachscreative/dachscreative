#!/usr/bin/env bash
# Render and install the systemd unit, then start Hermes as a managed service.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
need_root "$@"

command -v systemctl >/dev/null 2>&1 || die "systemd not available on this host; use scripts/run-foreground.sh instead"

model=$(model_path)
[ -n "$model" ] && [ -f "$model" ] || die "no model found - run 03-fetch-model.sh first"
[ -x "$HERMES_BIN_DIR/llama-server" ] || die "llama-server not built - run 02-build-llama.sh first"

unit=/etc/systemd/system/hermes.service
envfile=/etc/hermes.env

# An API key must not appear in the unit file, which is world-readable.
if [ -n "$HERMES_API_KEY" ]; then
  printf 'LLAMA_ARG_API_KEY=%s\n' "$HERMES_API_KEY" > "$envfile"
  chmod 0640 "$envfile"
  chown root:"$HERMES_SERVICE_USER" "$envfile"
  envline="EnvironmentFile=$envfile"
  ok "wrote API key to $envfile (mode 0640)"
else
  rm -f "$envfile"
  envline=""
fi

# PrivateDevices=yes hides /dev/nvidia*, which breaks GPU offload.
if has_cuda; then private_devices=no; else private_devices=yes; fi

sed \
  -e "s|__USER__|$HERMES_SERVICE_USER|g" \
  -e "s|__BIN__|$HERMES_BIN_DIR|g" \
  -e "s|__MODEL__|$model|g" \
  -e "s|__MODELDIR__|$HERMES_MODEL_DIR|g" \
  -e "s|__HOST__|$HERMES_HOST|g" \
  -e "s|__PORT__|$HERMES_PORT|g" \
  -e "s|__CTX__|$HERMES_CTX|g" \
  -e "s|__PARALLEL__|$HERMES_PARALLEL|g" \
  -e "s|__THREADS__|$(resolve_threads)|g" \
  -e "s|__NGL__|$(resolve_ngl)|g" \
  -e "s|__PRIVATE_DEVICES__|$private_devices|g" \
  -e "s|__ENVFILE__|$envline|g" \
  "$HERMES_ROOT/systemd/hermes.service.tmpl" > "$unit"

chmod 0644 "$unit"
ok "wrote $unit"

systemd-analyze verify "$unit" 2>&1 | grep -v '^$' && warn "systemd reported the notes above" || true

systemctl daemon-reload
systemctl enable hermes.service
info "starting hermes.service (loading several GB of weights - this can take a minute)"
systemctl restart hermes.service

# Wait for the HTTP endpoint rather than trusting the unit's own state.
for i in $(seq 1 120); do
  if curl -sf -m 2 "http://${HERMES_HOST}:${HERMES_PORT}/health" >/dev/null 2>&1; then
    ok "hermes.service is up and answering on ${HERMES_HOST}:${HERMES_PORT}"
    ok "verify with: ./scripts/05-smoke-test.sh"
    exit 0
  fi
  systemctl is-active --quiet hermes.service || {
    journalctl -u hermes.service -n 40 --no-pager >&2
    die "hermes.service failed to start (log above)"
  }
  sleep 2
done

journalctl -u hermes.service -n 40 --no-pager >&2
die "service started but did not answer on /health within 240s (log above)"
