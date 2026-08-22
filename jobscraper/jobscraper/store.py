"""SQLite store, and the new-since-last-run marking.

run.sh refuses to start a second run on top of a running one specifically to
protect this: two runs interleaving would each mark the other's finds as
already-seen and the "new today" list would come out empty.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .models import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    uid         TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    title       TEXT NOT NULL,
    company     TEXT NOT NULL,
    url         TEXT NOT NULL,
    location    TEXT,
    description TEXT,
    tags        TEXT,
    posted_at   TEXT,
    remote      INTEGER DEFAULT 0,
    score       REAL DEFAULT 0,
    matched     TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score);

CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    found      INTEGER DEFAULT 0,
    kept       INTEGER DEFAULT 0,
    new        INTEGER DEFAULT 0,
    status     TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        # WAL keeps a reader (an export, a manual query) from blocking the run.
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def known_uids(self) -> set[str]:
        with closing(self.conn.execute("SELECT uid FROM jobs")) as cur:
            return {row["uid"] for row in cur}

    def mark_new(self, jobs: list[Job]) -> list[Job]:
        """Set is_new on jobs this database has never seen. Writes nothing."""
        known = self.known_uids()
        for job in jobs:
            job.is_new = job.uid not in known
        return [j for j in jobs if j.is_new]

    def upsert(self, jobs: list[Job]) -> tuple[int, int]:
        """Insert new jobs, refresh last_seen on ones already stored."""
        now = _now()
        inserted = updated = 0
        for job in jobs:
            row = (
                job.uid,
                job.source,
                job.title,
                job.company,
                job.url,
                job.location,
                job.description,
                ",".join(job.tags),
                job.posted_at.isoformat() if job.posted_at else None,
                int(job.remote),
                job.score,
                ",".join(job.matched),
                now,
                now,
            )
            cur = self.conn.execute(
                """
                INSERT INTO jobs (uid, source, title, company, url, location,
                                  description, tags, posted_at, remote, score,
                                  matched, first_seen, last_seen)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(uid) DO UPDATE SET
                    last_seen = excluded.last_seen,
                    score     = excluded.score,
                    matched   = excluded.matched,
                    url       = excluded.url
                """,
                row,
            )
            # rowcount is 1 for both branches; compare timestamps to tell them
            # apart rather than guessing.
            existing = self.conn.execute(
                "SELECT first_seen FROM jobs WHERE uid = ?", (job.uid,)
            ).fetchone()
            if existing and existing["first_seen"] == now:
                inserted += 1
            else:
                updated += 1
            del cur
        self.conn.commit()
        return inserted, updated

    def start_run(self) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (started_at, status) VALUES (?, 'running')", (_now(),)
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, found: int, kept: int, new: int, status: str) -> None:
        self.conn.execute(
            "UPDATE runs SET ended_at=?, found=?, kept=?, new=?, status=? WHERE id=?",
            (_now(), found, kept, new, status, run_id),
        )
        self.conn.commit()

    def last_successful_run(self) -> str | None:
        row = self.conn.execute(
            "SELECT ended_at FROM runs WHERE status='ok' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["ended_at"] if row else None
