"""Greenhouse job boards.

Companies hosting on Greenhouse expose their board as JSON at a documented
endpoint. Point it at the boards you actually care about:

    [[sources]]
    name = "greenhouse"
    boards = ["stripe", "figma"]
"""

from __future__ import annotations

from typing import Iterable

from ..models import Job
from .base import Source, SourceError, ts


class Greenhouse(Source):
    name = "greenhouse"
    URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"

    def fetch(self) -> Iterable[Job]:
        boards = self.options.get("boards") or []
        if not boards:
            return []

        jobs: list[Job] = []
        for board in boards:
            url = self.URL.format(board=board)
            try:
                payload = self.get_json(url)
            except SourceError as exc:
                # One misspelled board name should not cost the other boards.
                print(f"    greenhouse/{board}: {exc}")
                continue

            for item in payload.get("jobs", []) if isinstance(payload, dict) else []:
                if not isinstance(item, dict):
                    continue
                location = (item.get("location") or {}).get("name", "")
                jobs.append(
                    Job(
                        source=self.name,
                        title=item.get("title", ""),
                        company=board,
                        url=item.get("absolute_url", ""),
                        location=location,
                        description=item.get("content", ""),
                        tags=[board],
                        posted_at=ts(item.get("updated_at") or item.get("created_at")),
                        remote="remote" in location.lower(),
                    )
                )

        return jobs
