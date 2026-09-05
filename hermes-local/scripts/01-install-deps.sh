#!/usr/bin/env bash
# Install build and runtime dependencies. Needs root (re-execs under sudo).
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
need_root "$@"

. /etc/os-release 2>/dev/null || true
case "${ID:-}" in
  ubuntu|debian) ;;
  *) die "this script targets Ubuntu/Debian; on ${ID:-this OS} install cmake, a C++ toolchain, git, curl and python3-venv by hand" ;;
esac

info "installing build dependencies via apt"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  build-essential cmake git curl ca-certificates pkg-config \
  libcurl4-openssl-dev python3 python3-venv python3-pip

ok "base dependencies installed"

if has_cuda; then
  info "NVIDIA driver present; checking for the CUDA toolkit"
  if command -v nvcc >/dev/null 2>&1; then
    ok "nvcc found: $(nvcc --version | awk '/release/{print $5,$6}')"
  else
    warn "nvidia-smi works but nvcc is missing - llama.cpp will build CPU-only."
    warn "To build with GPU support, install the CUDA toolkit first:"
    warn "  apt-get install -y nvidia-cuda-toolkit"
    warn "or use NVIDIA's official repo for a newer toolkit, then re-run 02-build-llama.sh."
  fi
else
  info "no NVIDIA GPU detected - building for CPU"
fi

info "creating service user '$HERMES_SERVICE_USER' and layout under $HERMES_PREFIX"
if ! id -u "$HERMES_SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$HERMES_SERVICE_USER"
  ok "created user $HERMES_SERVICE_USER"
else
  ok "user $HERMES_SERVICE_USER already exists"
fi

install -d -m 0755 "$HERMES_PREFIX" "$HERMES_BIN_DIR" "$(dirname "$HERMES_SRC_DIR")"
install -d -m 0755 -o "$HERMES_SERVICE_USER" -g "$HERMES_SERVICE_USER" "$HERMES_MODEL_DIR"

# Let the invoking (non-root) user build without sudo.
if [ -n "${SUDO_USER:-}" ]; then
  chown -R "$SUDO_USER" "$HERMES_PREFIX/src" "$HERMES_BIN_DIR" 2>/dev/null || true
fi

ok "dependencies ready - continue with 02-build-llama.sh"
