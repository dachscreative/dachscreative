#!/usr/bin/env bash
#
# macOS entry point. Double-click it in Finder, or let the LaunchAgent call it.
#
#   ./run.command                 normal run (VPN required)
#   ./run.command --dry-run       collect and score, write nothing
#   ./run.command --no-vpn-check  scrape without the VPN kill switch
#   ./run.command --no-pause      never wait for a keypress (the agent does this anyway)
#
# This is the sibling of ../run.sh, which stays as-is for Ubuntu. The two share
# the project, the venv layout, the log format and the exit codes; they differ
# only where macOS forces them to. The differences, all of them:
#
#   * No flock. flock(1) ships with util-linux and is simply not on a Mac.
#     Worse, it fails quietly here: `if ! flock -n 9` treats the shell's
#     127 "command not found" as "the lock is held", so every run would report
#     "another run is still in progress" and exit 0. Cron/launchd would never
#     complain and nothing would ever be collected. The lock below is built
#     from mkdir instead, which is atomic on every filesystem we care about.
#
#   * No stdbuf. Also GNU coreutils. `python -u` already does the job.
#
#   * The .command extension is what makes Finder run the file in Terminal
#     on a double-click.
#
set -uo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    echo "Run it as a program, not with 'source':   ./run.command" >&2
    return 1 2>/dev/null || exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"
LOCK_DIR="$ROOT/data/run.lock.d"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR" "$ROOT/data"

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
HOLD_LOCK=0

release_lock() {
    # Only the process that took the lock may drop it. Without this guard a run
    # that skipped because someone else held the lock would delete that other
    # run's lock on its way out.
    [[ $HOLD_LOCK -eq 1 ]] || return 0
    rm -rf "$LOCK_DIR" 2>/dev/null || true
    HOLD_LOCK=0
}

finish() {
    # Drop the lock BEFORE the pause below, for the same reason ../run.sh closes
    # fd 9 first: this process lives until someone presses Enter, and a window
    # left sitting at that prompt would otherwise block every later run.
    release_lock

    if [[ $SKIPPED -eq 1 ]]; then
        if [[ $PAUSE -eq 1 ]]; then
            echo
            echo "Skipped: another run still holds $LOCK_DIR. Nothing was collected."
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
        read -r -p "Press Enter to close this window... " _ || true
    fi
}
trap finish EXIT

if [[ ! -x "$PYTHON" ]]; then
    echo
    echo "  No virtualenv found at $PYTHON"
    echo "  Run macos/setup.sh first."
    echo
    STATUS=1
    exit $STATUS
fi

# ---------------------------------------------------------------------------
# The run lock.
#
# mkdir is atomic: two runs racing here, exactly one wins. The winner writes
# its pid, so a lock left behind by a crashed or force-quit run can be told
# apart from a live one and reclaimed. ../run.sh cannot do this - an flock is
# released by the kernel when the holder dies, so it has no stale case to
# recover from, but it also cannot survive being held by a window nobody is
# watching. This version recovers on its own.
# ---------------------------------------------------------------------------
acquire_lock() {
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        echo $$ > "$LOCK_DIR/pid"
        HOLD_LOCK=1
        return 0
    fi

    local pid
    pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"

    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        return 1              # a real run is alive and holding it
    fi

    # Stale. Reclaim it, then re-check that we are the one who did.
    echo "$(date '+%F %T') clearing stale lock from pid ${pid:-unknown}" >> "$LOG_DIR/cron.log"
    rm -rf "$LOCK_DIR" 2>/dev/null || true
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        echo $$ > "$LOCK_DIR/pid"
        HOLD_LOCK=1
        return 0
    fi
    return 1                  # someone else won the reclaim race
}

if ! acquire_lock; then
    echo "Another run is still in progress - skipping this one."
    echo "$(date '+%F %T') skipped, previous run still active" >> "$LOG_DIR/cron.log"
    SKIPPED=1
    STATUS=0
    exit $STATUS
fi

echo "$(date '+%F %T') starting run ${ARGS[*]:-}" >> "$LOG_DIR/cron.log"

"$PYTHON" -u -m jobscraper.cli run ${ARGS[@]+"${ARGS[@]}"}
STATUS=$?

exit $STATUS
