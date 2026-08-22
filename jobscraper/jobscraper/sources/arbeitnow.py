"""Arbeitnow. Free public job-board API, good coverage of the German market."""

from __future__ import annotations

from typing import Iterable

from ..models import Job
from .base import Source, ts


class Arbeitnow(Source):
    name = "arbeitnow"
    URL = "https://www.arbeitnow.com/api/job-board-api"

    def fetch(self) -> Iterable[Job]:
        pages = int(self.options.get("pages", 1))
        jobs: list[Job] = []
        url = self.URL

        for _ in range(max(1, pages)):
            payload = self.get_json(url)
            data = payload.get("data") if isinstance(payload, dict) else None
            if not data:
                break

            for item in data:
                if not isinstance(item, dict):
                    continue
                jobs.append(
                    Job(
                        source=self.name,
                        title=item.get("title", ""),
                        company=item.get("company_name", ""),
                        url=item.get("url", ""),
                        location=item.get("location", ""),
                        description=item.get("description", ""),
                        tags=list(item.get("tags") or []) + list(item.get("job_types") or []),
                        posted_at=ts(item.get("created_at")),
                        remote=bool(item.get("remote")),
                    )
                )

            nxt = (payload.get("links") or {}).get("next") if isinstance(payload, dict) else None
            if not nxt:
                break
            url = nxt

        return jobs
