#!/usr/bin/env bash
# Clone and build llama.cpp (the inference server). Auto-enables CUDA when the
# toolkit is present. Safe to re-run: updates the checkout and rebuilds.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

need_cmd git; need_cmd cmake; need_cmd curl

if [ ! -d "$HERMES_SRC_DIR/.git" ]; then
  info "cloning llama.cpp into $HERMES_SRC_DIR"
  mkdir -p "$(dirname "$HERMES_SRC_DIR")"
  git clone --depth 1 --branch "$HERMES_LLAMA_REF" \
    https://github.com/ggml-org/llama.cpp.git "$HERMES_SRC_DIR"
else
  info "updating existing llama.cpp checkout"
  git -C "$HERMES_SRC_DIR" fetch --depth 1 origin "$HERMES_LLAMA_REF"
  git -C "$HERMES_SRC_DIR" checkout -q FETCH_HEAD
fi
ok "llama.cpp at $(git -C "$HERMES_SRC_DIR" rev-parse --short HEAD)"

cmake_args=(
  -B "$HERMES_SRC_DIR/build"
  -S "$HERMES_SRC_DIR"
  -DCMAKE_BUILD_TYPE=Release
  -DLLAMA_CURL=ON
  -DLLAMA_BUILD_TESTS=OFF
  -DLLAMA_BUILD_EXAMPLES=OFF
  -DLLAMA_BUILD_SERVER=ON
  # Static link so the installed binary does not depend on the build tree.
  -DBUILD_SHARED_LIBS=OFF
)

if has_cuda && command -v nvcc >/dev/null 2>&1; then
  info "building with CUDA support"
  cmake_args+=(-DGGML_CUDA=ON)
else
  info "building CPU-only (no CUDA toolkit detected)"
fi

cmake "${cmake_args[@]}"
cmake --build "$HERMES_SRC_DIR/build" --config Release -j "$(nproc)" --target llama-server llama-cli

srv="$HERMES_SRC_DIR/build/bin/llama-server"
[ -x "$srv" ] || die "build finished but $srv is missing"

install -d -m 0755 "$HERMES_BIN_DIR"
install -m 0755 "$srv" "$HERMES_BIN_DIR/llama-server"
if [ -x "$HERMES_SRC_DIR/build/bin/llama-cli" ]; then
  install -m 0755 "$HERMES_SRC_DIR/build/bin/llama-cli" "$HERMES_BIN_DIR/llama-cli"
fi

# Shared ggml libraries, when built as shared objects.
find "$HERMES_SRC_DIR/build/bin" -maxdepth 1 -name '*.so' -exec install -m 0644 {} "$HERMES_BIN_DIR/" \; 2>/dev/null || true

ok "installed llama-server to $HERMES_BIN_DIR/llama-server"
"$HERMES_BIN_DIR/llama-server" --version 2>&1 | head -3 || true
ok "build complete - continue with 03-fetch-model.sh"
