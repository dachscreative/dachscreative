# jobscraper on macOS

The macOS packaging, kept separate from the Ubuntu side. Nothing here touches
`../run.sh` — that file stays exactly as it is and remains the entry point on
Ubuntu. On a Mac you use `run.command` instead.

```
jobscraper/
  run.sh          <- Ubuntu entry point (cron)         unchanged
  jobscraper/     <- the shared Python package
  macos/
    run.command   <- macOS entry point (Finder / launchd)
    setup.sh      <- builds ../.venv
    install-agent.sh / uninstall-agent.sh
    com.dachscreative.jobscraper.plist
```

## Install

```bash
cd jobscraper/macos
./setup.sh
./install-agent.sh            # or: ./install-agent.sh --at 07:30
```

Run it by hand at any time by double-clicking `run.command` in Finder, or
`open macos/run.command`. The flags match `run.sh`: `--dry-run`,
`--no-vpn-check`, `--no-pause`.

## Why a separate entry point rather than reusing run.sh

Three things in `run.sh` are Linux-only. Rather than add branching to a file
that works, macOS gets its own copy.

**`flock` does not exist on macOS.** It ships with util-linux. That alone would
be easy, but the failure is silent: `if ! flock -n 9` reads the shell's 127
"command not found" as "the lock is held", so *every* run would print "another
run is still in progress", write `skipped, previous run still active` to
`cron.log`, and exit 0. launchd would never report a problem and nothing would
ever be collected — and the log would blame a concurrent run that does not
exist.

`run.command` uses a `mkdir` lock instead. `mkdir` is atomic, so two runs
racing produce exactly one winner. The winner records its pid, which means a
lock left behind by a crashed or force-quit run can be told apart from a live
one and reclaimed automatically — the failure mode from 2026-08-21, where a
window sitting at the "Press Enter" prompt blocked every later run, cannot
recur here. The `finish` trap still drops the lock before the pause, for the
same reason `run.sh` closes fd 9 first, and a run that *skipped* never deletes
the lock it failed to take.

**`stdbuf` does not exist on macOS either.** `run.sh` already guards it with
`command -v` and falls through to plain `python -u`, so the macOS copy just
calls `python -u` directly.

**cron is the wrong scheduler.** It still runs, but under a TCC profile that
cannot read most of the home directory unless you grant Full Disk Access to
`/usr/sbin/cron` by hand. `install-agent.sh` writes a LaunchAgent instead.
A bonus: launchd runs a missed job when the Mac wakes, where cron would just
skip the day.

## Checking on it

```bash
launchctl print gui/$(id -u)/com.dachscreative.jobscraper | head -20
launchctl kickstart -p gui/$(id -u)/com.dachscreative.jobscraper   # run now
tail -f ../logs/cron.log
```

`logs/launchd.out.log` and `logs/launchd.err.log` catch anything written
before the scraper's own logging starts.

## Two things to know

The agent only runs while you are logged in. A `LaunchDaemon` would run
without a login session but could not reach a VPN configured per-user, which
the kill switch depends on — so this is a LaunchAgent deliberately.

Approve the file-access prompt on the first manual run. If the scraper writes
into Documents, Desktop or Downloads, macOS asks once. At 08:00 nobody is
there to click it, and the run stalls waiting.

## Not done yet

This packages the project to *run* on macOS. It does not build a
self-contained `.app`/`.dmg` — that needs `requirements.txt` and the
`jobscraper` package itself, and the bundle has to be built on a Mac
(py2app and PyInstaller cannot cross-compile).
