#!/usr/bin/env bash
# Report whether this machine can serve Hermes 4 14B at the configured quant,
# and what performance to expect. Read-only: changes nothing. Exit 1 if the
# machine cannot run the configured setup at all.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

# Approximate on-disk / in-memory size of Hermes 4 14B per quant, in GB.
quant_gb() {
  case "$1" in
    Q4_K_S) echo 8  ;;
    Q4_K_M) echo 9  ;;
    Q5_K_M) echo 11 ;;
    Q6_K)   echo 12 ;;
    Q8_0)   echo 16 ;;
    *)      echo 9  ;;
  esac
}

fail=0

info "Hermes local preflight"
echo

# --- OS ---
if [ -r /etc/os-release ]; then
  . /etc/os-release
  echo "  OS            : ${PRETTY_NAME:-unknown}"
  case "${ID:-}" in
    ubuntu|debian) ok "Debian-family detected; 01-install-deps.sh will use apt" ;;
    *) warn "not Ubuntu/Debian - install build deps manually (see README)" ;;
  esac
else
  warn "cannot read /etc/os-release"
fi

# --- CPU / RAM ---
cores=$(physical_cores); threads=$(nproc); ram=$(total_ram_gb)
echo "  CPU           : $cores physical cores / $threads logical"
echo "  RAM           : ${ram} GB"

need_gb=$(quant_gb "$HERMES_QUANT")
# Weights plus KV cache plus headroom. KV for 14B at 16k ctx is ~1-2 GB.
need_ram=$(( need_gb + 3 ))

# --- GPU ---
if has_cuda; then
  vram_mb=$(vram_total_mb); vram_gb=$(( vram_mb / 1024 ))
  echo "  GPU           : $(nvidia-smi --query-gpu=name --format=csv,noheader | paste -sd', ')"
  echo "  VRAM          : ${vram_gb} GB total"
  if [ "$vram_gb" -ge "$(( need_gb + 2 ))" ]; then
    ok "VRAM fits ${HERMES_QUANT} fully - expect roughly 30-60 tok/s"
  elif [ "$vram_gb" -ge 6 ]; then
    warn "VRAM is tight; llama.cpp will split layers between GPU and CPU (slower)"
    warn "set HERMES_NGL to a partial layer count (e.g. 24) if you hit OOM"
  else
    warn "little usable VRAM; this will run mostly on CPU"
  fi
else
  echo "  GPU           : none detected (CPU-only inference)"
fi

# --- Disk ---
target="$HERMES_PREFIX"
probe="$target"; while [ ! -d "$probe" ] && [ "$probe" != "/" ]; do probe=$(dirname "$probe"); done
avail_gb=$(df -BG --output=avail "$probe" 2>/dev/null | tail -1 | tr -dc '0-9')
echo "  Disk free     : ${avail_gb:-?} GB at $probe"

# llama.cpp source + build is ~2 GB; model is need_gb; leave a little slack.
need_disk=$(( need_gb + 4 ))
echo
info "Requirements for Hermes 4 14B @ ${HERMES_QUANT}"
echo "  model weights : ~${need_gb} GB"
echo "  RAM needed    : ~${need_ram} GB (weights + KV cache for ${HERMES_CTX} ctx)"
echo "  disk needed   : ~${need_disk} GB (model + llama.cpp build)"
echo

if [ -n "${avail_gb:-}" ] && [ "$avail_gb" -lt "$need_disk" ]; then
  warn "only ${avail_gb} GB free but ~${need_disk} GB needed"
  fail=1
else
  ok "disk space sufficient"
fi

if has_cuda && [ "$(vram_total_mb)" -ge $(( (need_gb + 2) * 1024 )) ]; then
  ok "GPU can hold the model; host RAM is not the constraint"
elif [ "$ram" -lt "$need_ram" ]; then
  warn "RAM is ${ram} GB but ~${need_ram} GB is needed for CPU inference"
  echo "       options: use a smaller quant (HERMES_QUANT=Q4_K_S), lower"
  echo "       HERMES_CTX, or add swap (slow)."
  fail=1
else
  ok "RAM sufficient for CPU inference"
  if ! has_cuda; then
    est=$(( cores * 2 / 3 ))
    [ "$est" -lt 1 ] && est=1
    echo "       expect roughly ${est}-$(( est * 2 )) tok/s on ${cores} cores - usable, not fast"
  fi
fi

# --- Network reachability of the Hub ---
echo
if curl -sS -o /dev/null -m 15 -w '' https://huggingface.co/api/models/gpt2 2>/dev/null; then
  ok "huggingface.co reachable"
else
  warn "cannot reach huggingface.co - 03-fetch-model.sh will fail"
  warn "check egress policy, proxy, or firewall before continuing"
fi

echo
if [ "$fail" -eq 0 ]; then
  ok "preflight passed - continue with 01-install-deps.sh"
else
  die "preflight found blocking problems (see warnings above)"
fi
