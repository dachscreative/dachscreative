#!/usr/bin/env bash
#
# Remove the daily LaunchAgent. Leaves the project, the venv and the data alone.
#
set -uo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    echo "Run it as a program, not with 'source':   ./uninstall-agent.sh" >&2
    return 1 2>/dev/null || exit 1
fi

LABEL="com.dachscreative.jobscraper"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 \
    || launchctl unload "$TARGET" >/dev/null 2>&1 \
    || true

if [[ -f "$TARGET" ]]; then
    rm -f "$TARGET"
    echo "Removed $TARGET"
else
    echo "Nothing to remove - $TARGET does not exist."
fi

if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "Warning: launchd still reports $LABEL. Try logging out and back in."
else
    echo "Agent unloaded."
fi
