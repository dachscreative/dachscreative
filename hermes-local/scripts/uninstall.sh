#!/usr/bin/env bash
# Remove the service and installed binaries. Keeps downloaded weights unless
# --purge is passed (they are large and slow to re-fetch).
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
need_root "$@"

purge=0
[ "${1:-}" = "--purge" ] && purge=1

if systemctl list-unit-files 2>/dev/null | grep -q '^hermes.service'; then
  info "stopping and disabling hermes.service"
  systemctl disable --now hermes.service || true
  rm -f /etc/systemd/system/hermes.service
  systemctl daemon-reload
  ok "service removed"
fi
rm -f /etc/hermes.env

info "removing binaries and build tree"
rm -rf "$HERMES_BIN_DIR" "$HERMES_PREFIX/src" "$HERMES_PREFIX/venv"

if [ "$purge" -eq 1 ]; then
  warn "purging model weights at $HERMES_MODEL_DIR"
  rm -rf "$HERMES_MODEL_DIR"
  if id -u "$HERMES_SERVICE_USER" >/dev/null 2>&1; then
    userdel "$HERMES_SERVICE_USER" || true
  fi
  rmdir "$HERMES_PREFIX" 2>/dev/null || true
  ok "fully removed"
else
  ok "removed; weights kept at $HERMES_MODEL_DIR (re-run with --purge to delete)"
fi
