#!/usr/bin/env bash
#
# One-time setup on a Mac. Builds the venv that macos/run.command expects.
#
#   ./setup.sh            create/update .venv and install dependencies
#   ./setup.sh --recreate throw the venv away first
#
# The venv lives at the project root (../.venv), the same place ../run.sh looks
# on Ubuntu. Only one of the two machines ever owns a given checkout, so there
# is no conflict - but keeping the path identical means the layout, the docs
# and the log lines stay the same on both.
#
set -uo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    echo "Run it as a program, not with 'source':   ./setup.sh" >&2
    return 1 2>/dev/null || exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
RECREATE=0
[[ "${1:-}" == "--recreate" ]] && RECREATE=1

die() { echo; echo "  $*"; echo; exit 1; }

# ---------------------------------------------------------------------------
# Find a python3. macOS ships one at /usr/bin/python3, but it is the Xcode
# command-line-tools stub: on a machine where the tools were never installed,
# invoking it pops a GUI dialog and fails. Prefer a real interpreter from
# Homebrew or python.org and fall back to the system one only if it works.
# ---------------------------------------------------------------------------
pick_python() {
    local candidates=(
        /opt/homebrew/bin/python3        # Apple silicon Homebrew
        /usr/local/bin/python3           # Intel Homebrew
        /Library/Frameworks/Python.framework/Versions/Current/bin/python3
    )
    local c
    for c in "${candidates[@]}"; do
        [[ -x "$c" ]] && { echo "$c"; return 0; }
    done
    # Anything else on PATH, then the system stub - but only if it actually runs.
    c="$(command -v python3 2>/dev/null || true)"
    if [[ -n "$c" ]] && "$c" -c 'import sys' >/dev/null 2>&1; then
        echo "$c"; return 0
    fi
    return 1
}

PY="$(pick_python)" || die "No working python3 found.
  Install one with:  brew install python
  or from https://www.python.org/downloads/macos/"

# The venv module is a separate package on some distributions of python.
"$PY" -c 'import venv' >/dev/null 2>&1 \
    || die "$PY has no venv module. Install a full python3 (brew install python)."

VER="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "Using $PY (python $VER)"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
    || die "python $VER is too old. Need 3.9 or newer."

if [[ $RECREATE -eq 1 && -d "$VENV" ]]; then
    echo "Removing existing venv at $VENV"
    rm -rf "$VENV"
fi

if [[ ! -d "$VENV" ]]; then
    echo "Creating venv at $VENV"
    "$PY" -m venv "$VENV" || die "Could not create the venv."
fi

VPY="$VENV/bin/python"
[[ -x "$VPY" ]] || die "The venv looks broken - no interpreter at $VPY.
  Try:  ./setup.sh --recreate"

echo "Upgrading pip"
"$VPY" -m pip install --quiet --upgrade pip || die "Could not upgrade pip."

if [[ -f "$ROOT/requirements.txt" ]]; then
    echo "Installing from requirements.txt"
    "$VPY" -m pip install --quiet -r "$ROOT/requirements.txt" \
        || die "Dependency install failed. Re-run without --quiet to see why:
  $VPY -m pip install -r $ROOT/requirements.txt"
elif [[ -f "$ROOT/pyproject.toml" ]]; then
    echo "Installing from pyproject.toml"
    "$VPY" -m pip install --quiet -e "$ROOT" \
        || die "Dependency install failed. Re-run without --quiet to see why:
  $VPY -m pip install -e $ROOT"
else
    die "Neither requirements.txt nor pyproject.toml found in $ROOT.
  Copy the project's dependency file across before running setup."
fi

mkdir -p "$ROOT/data" "$ROOT/logs" "$ROOT/exports"

# Prove the entry point actually imports before declaring success. A venv that
# builds fine but cannot reach jobscraper.cli is the failure that would
# otherwise only show up at 08:00 the next morning, in a log nobody reads.
if "$VPY" -c 'import jobscraper.cli' >/dev/null 2>&1; then
    echo "jobscraper.cli imports cleanly"
else
    echo
    echo "  Warning: 'import jobscraper.cli' failed."
    echo "  The venv is built, but the package is not importable from $ROOT."
    echo "  Check that the jobscraper/ package sits next to this macos/ folder."
    echo
fi

echo
echo "Setup done."
echo "  Run it by hand:   open $HERE/run.command"
echo "  Schedule it:      $HERE/install-agent.sh"
echo
