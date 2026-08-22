"""Exports.

run.sh tells the user "Exports are in $ROOT/exports/" when a run succeeds, so
that is where these land. Two files per run:

  jobs-YYYY-MM-DD.csv   everything kept, for filtering in a spreadsheet
  new-YYYY-MM-DD.md     only what is new since the last run, for reading

plus latest.csv / latest.md rewritten each run, so a bookmark or a script has a
stable path to point at.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from .models import Job

FIELDS = [
    "score",
    "is_new",
    "title",
    "company",
    "location",
    "remote",
    "source",
    "posted_at",
    "url",
    "matched",
]


def _row(job: Job) -> dict[str, str]:
    return {
        "score": f"{job.score:.2f}",
        "is_new": "yes" if job.is_new else "",
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote": "yes" if job.remote else "",
        "source": job.source,
        "posted_at": job.posted_at.strftime("%Y-%m-%d") if job.posted_at else "",
        "url": job.url,
        "matched": ", ".join(job.matched),
    }


def write_csv(path: Path, jobs: list[Job]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for job in jobs:
            writer.writerow(_row(job))
    return path


def write_markdown(path: Path, jobs: list[Job], title: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", ""]

    if not jobs:
        lines += ["Nothing new in this run.", ""]
    else:
        lines += [f"{len(jobs)} posting(s), best first.", ""]
        for job in jobs:
            where = job.location or ("Remote" if job.remote else "unspecified")
            when = job.posted_at.strftime("%Y-%m-%d") if job.posted_at else "date unknown"
            company = job.company or "unknown company"
            lines.append(f"## {job.title} — {company}")
            lines.append("")
            lines.append(f"- **Score** {job.score:.2f} ({', '.join(job.matched) or 'no terms'})")
            lines.append(f"- **Where** {where} · **Posted** {when} · **Via** {job.source}")
            lines.append(f"- <{job.url}>")
            lines.append("")
            snippet = " ".join(job.description.split())[:400]
            if snippet:
                lines.append(f"> {snippet}…")
                lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def export_all(exports_dir: Path, kept: list[Job], new: list[Job]) -> list[Path]:
    stamp = date.today().isoformat()
    written = [
        write_csv(exports_dir / f"jobs-{stamp}.csv", kept),
        write_markdown(exports_dir / f"new-{stamp}.md", new, f"New postings — {stamp}"),
        write_csv(exports_dir / "latest.csv", kept),
        write_markdown(exports_dir / "latest.md", new, f"New postings — {stamp}"),
    ]
    return written
