"""RemoteOK. Documented public JSON feed at /api."""

from __future__ import annotations

from typing import Iterable

from ..models import Job
from .base import Source, ts


class RemoteOK(Source):
    name = "remoteok"
    URL = "https://remoteok.com/api"

    def fetch(self) -> Iterable[Job]:
        payload = self.get_json(self.URL)
        if not isinstance(payload, list):
            return []

        jobs = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            # The first element is a legal notice, not a posting.
            if not item.get("id") or not item.get("position"):
                continue
            jobs.append(
                Job(
                    source=self.name,
                    title=item.get("position", ""),
                    company=item.get("company", ""),
                    url=item.get("url") or f"https://remoteok.com/l/{item.get('id')}",
                    location=item.get("location", "") or "Remote",
                    description=item.get("description", ""),
                    tags=list(item.get("tags") or []),
                    posted_at=ts(item.get("epoch") or item.get("date")),
                    remote=True,
                )
            )
        return jobs
