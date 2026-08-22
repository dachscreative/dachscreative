#!/usr/bin/env bash
#
# Install the daily LaunchAgent. This is the macOS stand-in for the crontab
# line used on Ubuntu.
#
#   ./install-agent.sh              schedule the daily run at 08:00
#   ./install-agent.sh --at 07:30   pick a different time
#
set -uo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    echo "Run it as a program, not with 'source':   ./install-agent.sh" >&2
    return 1 2>/dev/null || exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

LABEL="com.dachscreative.jobscraper"
TEMPLATE="$HERE/$LABEL.plist"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

HOUR=8
MINUTE=0

die() { echo; echo "  $*"; echo; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --at)
            [[ $# -ge 2 ]] || die "--at needs a time, e.g. --at 07:30"
            [[ "$2" =~ ^([0-9]{1,2}):([0-9]{2})$ ]] || die "Bad time '$2'. Use HH:MM, e.g. 07:30"
            HOUR=$((10#${BASH_REMATCH[1]}))
            MINUTE=$((10#${BASH_REMATCH[2]}))
            (( HOUR < 24 && MINUTE < 60 )) || die "Bad time '$2'. Hour must be 0-23, minute 0-59."
            shift 2
            ;;
        *) die "Unknown option '$1'" ;;
    esac
done

[[ -f "$TEMPLATE" ]] || die "Missing plist template at $TEMPLATE"
[[ -x "$HERE/run.command" ]] || die "run.command is missing or not executable.
  chmod +x $HERE/run.command"
[[ -x "$ROOT/.venv/bin/python" ]] || die "No venv yet. Run ./setup.sh first."

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/logs"

# Substitute the real project path and the chosen time. Using python keeps the
# plist valid rather than trusting sed to produce well-formed XML.
python3 - "$TEMPLATE" "$TARGET" "$ROOT" "$HOUR" "$MINUTE" <<'PY' || die "Could not write $TARGET"
import plistlib, sys
template, target, root, hour, minute = sys.argv[1:6]
raw = open(template, "rb").read().replace(b"__ROOT__", root.encode())
data = plistlib.loads(raw)
data["StartCalendarInterval"] = {"Hour": int(hour), "Minute": int(minute)}
with open(target, "wb") as fh:
    plistlib.dump(data, fh)
PY

# launchctl gained bootstrap/bootout in 10.11 and deprecated load/unload. Use
# the modern pair where it exists and fall back quietly where it does not.
DOMAIN="gui/$(id -u)"
if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "Replacing the existing agent"
    launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
fi

if ! launchctl bootstrap "$DOMAIN" "$TARGET" 2>/dev/null; then
    launchctl unload "$TARGET" >/dev/null 2>&1 || true
    launchctl load "$TARGET" 2>/dev/null || die "launchctl refused to load $TARGET
  Check it with:  plutil -lint $TARGET"
fi

printf 'Scheduled: %s daily at %02d:%02d\n' "$LABEL" "$HOUR" "$MINUTE"
echo "  plist:    $TARGET"
echo "  logs:     $ROOT/logs/cron.log"
echo "  check:    launchctl print $DOMAIN/$LABEL | head -20"
echo "  run now:  launchctl kickstart -p $DOMAIN/$LABEL"
echo "  remove:   $HERE/uninstall-agent.sh"
echo
echo "Note: the agent runs only while you are logged in. The first run will"
echo "ask for permission if the scraper touches Documents/Desktop/Downloads -"
echo "approve it once, at 08:00 nobody will be there to click."
