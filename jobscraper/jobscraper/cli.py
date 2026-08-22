"""Command line entry point.

    python -m jobscraper.cli run [--dry-run] [--no-vpn-check]

Exit codes, because run.sh reads them and says different things about each:

    0    the run finished
    1    something went wrong
    2    aborted before scraping: the VPN check failed
    130  Ctrl+C
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import __version__, vpn
from .config import Config, ConfigError, load as load_config
from .export import export_all
from .models import Job
from .scoring import Scorer
from .sources import SourceError, build as build_source
from .store import Store

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_VPN = 2
EXIT_INTERRUPT = 130

log = logging.getLogger("jobscraper")


def project_root() -> Path:
    # jobscraper/cli.py -> jobscraper/ -> project root
    return Path(__file__).resolve().parent.parent


def setup_logging(root: Path) -> None:
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    # run.sh points the user at logs/YYYY-MM.log on failure, so that is the name.
    logfile = log_dir / f"{datetime.now():%Y-%m}.log"

    log.setLevel(logging.DEBUG)
    # Close before dropping: repeated setup (tests, or a long-lived process)
    # would otherwise leak an open file handle per call.
    for handler in list(log.handlers):
        handler.close()
    log.handlers.clear()

    to_file = logging.FileHandler(logfile, encoding="utf-8")
    to_file.setLevel(logging.DEBUG)
    to_file.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    log.addHandler(to_file)

    # The console gets the progress lines only. run.sh runs us with python -u
    # so these arrive as they happen rather than in a lump at the end.
    to_console = logging.StreamHandler(sys.stdout)
    to_console.setLevel(logging.INFO)
    to_console.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(to_console)


def collect(cfg: Config) -> tuple[list[Job], int]:
    """Fetch from every enabled source. A dead source costs its own results only."""
    jobs: list[Job] = []
    failures = 0

    if not cfg.sources:
        log.warning("No sources enabled - check the [[sources]] tables in config.toml")
        return jobs, failures

    for spec in cfg.sources:
        name = spec.get("name", "?")
        try:
            source = build_source(spec, cfg.request_timeout, cfg.request_delay, cfg.user_agent)
            found = list(source.fetch())
            jobs.extend(found)
            log.info("  %-16s %4d postings", name, len(found))
        except SourceError as exc:
            failures += 1
            log.warning("  %-16s failed: %s", name, exc)
        except Exception as exc:  # noqa: BLE001 - one source must not kill the run
            failures += 1
            log.warning("  %-16s failed: %s", name, exc)
            log.debug("traceback for %s", name, exc_info=True)

    return jobs, failures


def apply_filters(jobs: list[Job], cfg: Config) -> list[Job]:
    f = cfg.filters
    cutoff = datetime.now(timezone.utc) - timedelta(days=f.posted_within_days)
    kept = []

    for job in jobs:
        if not job.url or not job.title:
            continue
        # A posting with no date is kept: several feeds omit it, and dropping
        # them would quietly discard whole sources.
        if job.posted_at and job.posted_at < cutoff:
            continue
        if f.remote_only and not job.remote:
            continue
        if f.locations:
            haystack = f"{job.location} {'remote' if job.remote else ''}".lower()
            if not any(loc in haystack for loc in f.locations):
                continue
        kept.append(job)

    return kept


def deduplicate(jobs: list[Job]) -> list[Job]:
    """Same posting from two sources: keep the one that scored higher."""
    best: dict[str, Job] = {}
    for job in jobs:
        current = best.get(job.uid)
        if current is None or job.score > current.score:
            best[job.uid] = job
    return list(best.values())


def cmd_run(args: argparse.Namespace, root: Path) -> int:
    cfg = load_config(root)

    log.info("jobscraper %s - %s", __version__, datetime.now().strftime("%Y-%m-%d %H:%M"))
    if args.dry_run:
        log.info("dry run: nothing will be written")

    # -- the kill switch, before a single request to a job board -------------
    if args.no_vpn_check:
        log.warning("VPN check skipped (--no-vpn-check)")
    else:
        log.info("Checking VPN...")
        status = vpn.check(cfg.vpn, cfg.user_agent)
        if not status.ok:
            log.error("VPN check failed: %s", status.reason)
            return EXIT_VPN
        log.info("  ok - %s", status.reason)

    log.info("Collecting from %d source(s)...", len(cfg.sources))
    jobs, failures = collect(cfg)
    found = len(jobs)
    log.info("  %d postings collected", found)

    if failures and failures == len(cfg.sources):
        log.error("Every source failed - not writing anything over good data.")
        return EXIT_ERROR

    jobs = apply_filters(jobs, cfg)
    log.info("  %d after filters", len(jobs))

    scorer = Scorer(cfg.scoring)
    if not cfg.scoring.include:
        log.warning("No [scoring.include] terms configured - everything scores 0")
    for job in jobs:
        job.score, job.matched = scorer.score(job)

    kept = [j for j in jobs if scorer.keeps(j.score)]
    kept = deduplicate(kept)
    kept.sort(key=lambda j: (-j.score, j.company.lower(), j.title.lower()))
    log.info("  %d scoring at or above %.1f", len(kept), cfg.scoring.min_score)

    store = Store(root / "data" / "jobs.db")
    run_id = None
    try:
        new = store.mark_new(kept)
        log.info("  %d new since the last run", len(new))

        if args.dry_run:
            for job in kept[: args.limit]:
                flag = "NEW " if job.is_new else "    "
                log.info("    %s%6.2f  %s - %s", flag, job.score, job.title, job.company or "?")
            log.info("Dry run: no database write, no exports.")
            return EXIT_OK

        run_id = store.start_run()
        inserted, updated = store.upsert(kept)
        log.debug("stored: %d inserted, %d updated", inserted, updated)

        written = export_all(root / "exports", kept, new)
        for path in written:
            log.info("  wrote %s", path.relative_to(root))

        store.finish_run(run_id, found, len(kept), len(new), "ok")
        run_id = None
    finally:
        if run_id is not None:
            store.finish_run(run_id, found, len(kept), 0, "failed")
        store.close()

    log.info("Done: %d collected, %d kept, %d new.", found, len(kept), len(new))
    return EXIT_OK


def cmd_check_vpn(args: argparse.Namespace, root: Path) -> int:
    cfg = load_config(root)
    status = vpn.check(cfg.vpn, cfg.user_agent)
    print(("ok:     " if status.ok else "FAILED: ") + status.reason)
    if status.interface:
        print(f"        interface: {status.interface}")
    if status.public_ip:
        print(f"        public IP: {status.public_ip}")
    return EXIT_OK if status.ok else EXIT_VPN


def cmd_sources(args: argparse.Namespace, root: Path) -> int:
    from .sources import REGISTRY

    cfg = load_config(root)
    enabled = {str(s.get("name", "")).lower() for s in cfg.sources}
    print("Available sources:")
    for name in sorted(REGISTRY):
        print(f"  {'[on] ' if name in enabled else '[off]'} {name}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobscraper",
        description="Collect job postings, score them, export what is new.",
    )
    parser.add_argument("--version", action="version", version=f"jobscraper {__version__}")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="the daily run")
    run.add_argument("--dry-run", action="store_true", help="collect and score, write nothing")
    run.add_argument("--no-vpn-check", action="store_true", help="scrape without the kill switch")
    run.add_argument("--limit", type=int, default=20, help="rows to print in a dry run")
    run.set_defaults(func=cmd_run)

    check = sub.add_parser("check-vpn", help="run the kill switch check and report")
    check.set_defaults(func=cmd_check_vpn)

    srcs = sub.add_parser("sources", help="list sources and whether they are enabled")
    srcs.set_defaults(func=cmd_sources)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_ERROR

    root = project_root()
    setup_logging(root)

    try:
        return int(args.func(args, root))
    except KeyboardInterrupt:
        # Without this, python prints a traceback and exits 1, and run.sh would
        # report "run failed" for what was someone pressing Ctrl+C.
        log.warning("Interrupted.")
        return EXIT_INTERRUPT
    except ConfigError as exc:
        log.error("Config error: %s", exc)
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001
        log.error("Unexpected failure: %s", exc)
        log.debug("traceback", exc_info=True)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
