#!/usr/bin/env bash
#
# Daily entry point. This is what cron calls.
#
#   ./run.sh                 normal run (VPN required)
#   ./run.sh --dry-run       collect and score, write nothing
#   ./run.sh --no-vpn-check  scrape without the VPN kill switch
#   ./run.sh --no-pause      never wait for a keypress (cron does this anyway)
#
set -uo pipefail

# ---------------------------------------------------------------------------
# Running this with `source run.sh` or `. run.sh` would make the exit calls
# below close the terminal itself. Refuse, and explain.
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    echo "Run it as a program, not with 'source':   ./run.sh" >&2
    return 1 2>/dev/null || exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"
LOCK="$ROOT/data/run.lock"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR" "$ROOT/data"

# Pause before closing only when a human is watching an interactive terminal.
# Under cron stdin is not a tty, so this switches itself off.
PAUSE=1
ARGS=()
for arg in "$@"; do
    case "$arg" in
        --no-pause) PAUSE=0 ;;
        *) ARGS+=("$arg") ;;
    esac
done
[[ -t 0 && -t 1 ]] || PAUSE=0

STATUS=1
SKIPPED=0
finish() {
    # Release the run lock BEFORE the pause below. The lock lives on file
    # descriptor 9 and is held for as long as this process lives - and the
    # process lives until someone presses Enter. A window left sitting at that
    # prompt therefore blocked every later run, cron included, which is exactly
    # what happened after the 2026-08-21 runs: the next invocation reported
    # "another run is still in progress" while nothing was running at all.
    exec 9>&- 2>/dev/null || true

    if [[ $SKIPPED -eq 1 ]]; then
        if [[ $PAUSE -eq 1 ]]; then
            echo
            echo "Skipped: another run still holds $LOCK. Nothing was collected."
            echo "If no run is actually active, close the old jobscraper window"
            echo "or:  pkill -f jobscraper.cli"
            echo
            read -r -p "Press Enter to close this window... " _ || true
        fi
        return
    fi

    case $STATUS in
        0)   echo "$(date '+%F %T') run finished ok" >> "$LOG_DIR/cron.log" ;;
        2)   echo "$(date '+%F %T') ABORTED: VPN check failed" >> "$LOG_DIR/cron.log" ;;
        130) echo "$(date '+%F %T') interrupted by user" >> "$LOG_DIR/cron.log" ;;
        *)   echo "$(date '+%F %T') run failed with status $STATUS" >> "$LOG_DIR/cron.log" ;;
    esac

    if [[ $PAUSE -eq 1 ]]; then
        echo
        case $STATUS in
            0) echo "Finished. Exports are in $ROOT/exports/" ;;
            2) echo "Stopped before scraping: the VPN check failed (see above)." ;;
            130) echo "Stopped on Ctrl+C." ;;
            *) echo "Run failed (exit $STATUS). Full log: $LOG_DIR/$(date '+%Y-%m').log" ;;
        esac
        echo
        # This is what keeps the window open. Without it a launcher-started
        # terminal closes the instant the script exits and the error is lost.
        read -r -p "Press Enter to close this window... " _ || true
    fi
}
trap finish EXIT

if [[ ! -x "$PYTHON" ]]; then
    echo
    echo "  No virtualenv found at $PYTHON"
    echo "  Run ./setup.sh first."
    echo
    STATUS=1
    exit $STATUS
fi

# Refuse to start a second run on top of a running one. cron plus a slow scrape
# would otherwise interleave two runs and corrupt the new-since-last-run marking.
exec 9>"$LOCK"
if ! flock -n 9; then
    echo "Another run is still in progress - skipping this one."
    echo "$(date '+%F %T') skipped, previous run still active" >> "$LOG_DIR/cron.log"
    # Exit 0 so cron does not mail a failure for a deliberate skip, but flag it
    # so the closing message says "skipped" rather than "Finished. Exports are
    # in ..." - the old wording announced success for a run that never started.
    SKIPPED=1
    STATUS=0
    exit $STATUS
fi

echo "$(date '+%F %T') starting run ${ARGS[*]:-}" >> "$LOG_DIR/cron.log"

# stdbuf keeps the progress lines flowing to the terminal instead of sitting in
# a 4KB pipe buffer when the output is piped or teed.
if command -v stdbuf >/dev/null 2>&1; then
    stdbuf -oL -eL "$PYTHON" -u -m jobscraper.cli run ${ARGS[@]+"${ARGS[@]}"}
else
    "$PYTHON" -u -m jobscraper.cli run ${ARGS[@]+"${ARGS[@]}"}
fi
STATUS=$?

exit $STATUS
