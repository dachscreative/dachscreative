#!/usr/bin/env bash
#
# One-time setup on Ubuntu. Builds the venv that run.sh expects at .venv/.
#
#   ./setup.sh            create/update .venv and install dependencies
#   ./setup.sh --recreate throw the venv away first
#
set -uo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    echo "Run it as a program, not with 'source':   ./setup.sh" >&2
    return 1 2>/dev/null || exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
RECREATE=0
[[ "${1:-}" == "--recreate" ]] && RECREATE=1

die() { echo; echo "  $*"; echo; exit 1; }

command -v python3 >/dev/null 2>&1 || die "python3 not found.
  sudo apt install python3 python3-venv"

VER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
    || die "python $VER is too old. Need 3.9 or newer."
echo "Using $(command -v python3) (python $VER)"

# On Debian/Ubuntu venv is split into its own package and the failure message
# from `python3 -m venv` is not obvious about it.
python3 -c 'import venv' >/dev/null 2>&1 \
    || die "The venv module is missing.
  sudo apt install python3-venv"

# flock lives in util-linux and is effectively always present, but run.sh
# depends on it completely, so say so now rather than at 08:00 tomorrow.
command -v flock >/dev/null 2>&1 \
    || die "flock not found - run.sh needs it for the run lock.
  sudo apt install util-linux"

if [[ $RECREATE -eq 1 && -d "$VENV" ]]; then
    echo "Removing existing venv at $VENV"
    rm -rf "$VENV"
fi

if [[ ! -d "$VENV" ]]; then
    echo "Creating venv at $VENV"
    python3 -m venv "$VENV" || die "Could not create the venv.
  sudo apt install python3-venv"
fi

VPY="$VENV/bin/python"
[[ -x "$VPY" ]] || die "The venv looks broken - no interpreter at $VPY.
  Try:  ./setup.sh --recreate"

echo "Upgrading pip"
"$VPY" -m pip install --quiet --upgrade pip || die "Could not upgrade pip."

echo "Installing dependencies"
"$VPY" -m pip install --quiet -r "$ROOT/requirements.txt" || die "Dependency install failed. Re-run to see why:
  $VPY -m pip install -r $ROOT/requirements.txt"

mkdir -p "$ROOT/data" "$ROOT/logs" "$ROOT/exports"

if [[ ! -f "$ROOT/config.toml" ]]; then
    cp "$ROOT/config.example.toml" "$ROOT/config.toml"
    echo "Created config.toml from the example - edit it before the first real run."
fi

"$VPY" -c 'import jobscraper.cli' >/dev/null 2>&1 \
    || die "The venv is built but 'import jobscraper.cli' fails.
  Check that the jobscraper/ package sits next to this script."

echo
echo "Setup done."
echo "  Try it:      ./run.sh --dry-run --no-vpn-check"
echo "  Check VPN:   .venv/bin/python -m jobscraper.cli check-vpn"
echo "  Schedule it: crontab -e   ->   0 8 * * *  $ROOT/run.sh --no-pause"
echo
