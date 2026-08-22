# jobscraper

Collects job postings from a few boards once a day, scores them against terms
you care about, and exports what is new since the last run.

Runs on Ubuntu via `run.sh` + cron. macOS support lives in [`macos/`](macos/)
and is a separate entry point — `run.sh` is not used there.

## Setup

```bash
./setup.sh
cp config.example.toml config.toml   # setup.sh does this for you
$EDITOR config.toml
```

Then try it without touching anything:

```bash
./run.sh --dry-run --no-vpn-check
```

## Daily use

```bash
./run.sh                  # the real thing: VPN required, writes exports
./run.sh --dry-run        # collect and score, write nothing
./run.sh --no-vpn-check   # scrape without the kill switch
./run.sh --no-pause       # never wait for a keypress
```

Schedule it:

```
0 8 * * *  /path/to/jobscraper/run.sh --no-pause
```

## Output

One Excel workbook per run, in `exports/`:

| File | What |
|---|---|
| `jobs_YYYY-MM-DD.xlsx` | the run's workbook |
| `latest.xlsx` | rewritten each run, a stable path to bookmark |

Each workbook has two sheets:

| Sheet | What |
|---|---|
| `Jobs` | everything kept, best score first |
| `New` | only what is new since the last run |

Both sheets get a frozen header, an autofilter, scores as real numbers, dates
as real dates (so they sort correctly), and the URL as a clickable link. New
rows are shaded green on the `Jobs` sheet.

The underscore in `jobs_YYYY-MM-DD.xlsx` is deliberate: `run.sh` reports the
newest export with `ls -1t exports/jobs_*.xlsx`, and a hyphen would not match.

State lives in `data/jobs.db` (SQLite). Logs are `logs/YYYY-MM.log` for detail
and `logs/cron.log` for one line per run.

## Exit codes

`run.sh` reads these and says something different about each, so they are part
of the interface:

| Code | Meaning |
|---|---|
| 0 | ran to completion |
| 1 | something went wrong |
| 2 | aborted before scraping — the VPN check failed |
| 130 | Ctrl+C |

## The VPN kill switch

Nothing is requested from a job board until the VPN check passes. Two
independent conditions, both required:

1. A VPN interface is up (`tun*`, `wg*`, `ppp*`, and `utun*` on macOS).
2. The public IP is not one of `vpn.blocked_ips`.

Fill in `blocked_ips` with your real address, found **with the VPN off**:

```bash
curl -s https://api.ipify.org
```

Without that list the check can only confirm an interface exists, not that
traffic is actually using it. It fails closed: if the IP cannot be verified and
a blocklist is configured, the run aborts rather than assuming it is safe.

Check it on its own:

```bash
.venv/bin/python -m jobscraper.cli check-vpn
```

## Configuration

`config.toml`, all of it optional but the scoring section is what makes this
useful. See `config.example.toml` for the full annotated set.

- `[[sources]]` — which boards. `remoteok`, `arbeitnow`, `weworkremotely`,
  `greenhouse` (point it at company board slugs). Toggle with `enabled`.
- `[filters]` — `posted_within_days`, `remote_only`, `locations`.
- `[scoring.include]` / `[scoring.exclude]` — `term = weight`. A term in the
  title counts `title_multiplier` times. Anything below `min_score` is dropped.
- `[http]` — `delay` is the pause between requests per source. These are free
  public endpoints; leave it at 1s or higher.

List what is wired up:

```bash
.venv/bin/python -m jobscraper.cli sources
```

## How a run goes

```
VPN check → collect → filter → score → drop below min_score
          → deduplicate → mark new → write db → export
```

A source that fails costs only its own results; the run continues. If *every*
source fails the run exits 1 without writing, so a total network outage cannot
overwrite good exports with an empty file.

Postings are identified by company + normalised title, not URL. A job re-posted
at a new URL is not announced as new again, and the same job syndicated to two
boards collapses into one entry.

## Tests

No network, no extra dependencies:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Layout

```
run.sh              Ubuntu entry point
setup.sh            builds .venv
config.example.toml
jobscraper/
  cli.py            entry point and the run pipeline
  config.py         TOML loading
  vpn.py            the kill switch
  models.py         the Job shape, HTML cleaning, identity
  scoring.py        keyword scoring
  store.py          SQLite, new-since-last-run
  export.py         xlsx workbook
  sources/          remoteok, arbeitnow, weworkremotely, greenhouse
tests/
macos/              separate macOS packaging, see macos/README.md
```
