# Shared helpers. Sourced by every script; not executable on its own.
set -euo pipefail

HERMES_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../config.env
source "$HERMES_ROOT/config.env"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YEL=$'\033[33m'; C_BLU=$'\033[34m'; C_RST=$'\033[0m'
else
  C_RED=''; C_GRN=''; C_YEL=''; C_BLU=''; C_RST=''
fi

info()  { printf '%s==>%s %s\n' "$C_BLU" "$C_RST" "$*"; }
ok()    { printf '%s ok %s %s\n' "$C_GRN" "$C_RST" "$*"; }
warn()  { printf '%swarn%s %s\n' "$C_YEL" "$C_RST" "$*" >&2; }
die()   { printf '%sfail%s %s\n' "$C_RED" "$C_RST" "$*" >&2; exit 1; }

need_cmd() { command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"; }

# Re-exec under sudo when a step needs root. Callers: need_root "$@"
need_root() {
  if [ "$(id -u)" -ne 0 ]; then
    command -v sudo >/dev/null 2>&1 || die "this step needs root and sudo is not installed"
    info "escalating with sudo"
    exec sudo -E "$0" "$@"
  fi
}

physical_cores() {
  local c
  c=$(lscpu -p=Core,Socket 2>/dev/null | grep -vc '^#' || true)
  if [ -n "$c" ] && [ "$c" -gt 0 ] 2>/dev/null; then
    lscpu -p=Core,Socket 2>/dev/null | grep -v '^#' | sort -u | wc -l
  else
    nproc
  fi
}

has_cuda() { command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; }

total_ram_gb() { awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo; }

vram_total_mb() {
  has_cuda || { echo 0; return; }
  nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null \
    | awk '{s+=$1} END {print s+0}'
}

resolve_threads() {
  if [ "$HERMES_THREADS" = "auto" ]; then physical_cores; else echo "$HERMES_THREADS"; fi
}

resolve_ngl() {
  if [ "$HERMES_NGL" = "auto" ]; then
    if has_cuda; then echo 999; else echo 0; fi
  else
    echo "$HERMES_NGL"
  fi
}

# Path to the model file on disk, resolving auto-discovery marker if present.
model_path() {
  if [ -n "$HERMES_MODEL_FILE" ]; then
    echo "$HERMES_MODEL_DIR/$HERMES_MODEL_FILE"
  elif [ -f "$HERMES_MODEL_DIR/.selected" ]; then
    echo "$HERMES_MODEL_DIR/$(cat "$HERMES_MODEL_DIR/.selected")"
  else
    echo ""
  fi
}
