"""We Work Remotely. Published RSS feeds, parsed with the stdlib.

feedparser would be one line shorter and one dependency heavier. RSS is simple
enough that ElementTree covers it.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Iterable

from ..models import Job
from .base import Source, SourceError, ts

DEFAULT_CATEGORIES = ["remote-programming-jobs"]


class WeWorkRemotely(Source):
    name = "weworkremotely"
    URL = "https://weworkremotely.com/categories/{category}.rss"

    def fetch(self) -> Iterable[Job]:
        categories = self.options.get("categories") or DEFAULT_CATEGORIES
        jobs: list[Job] = []

        for category in categories:
            url = self.URL.format(category=category)
            text = self.get_text(url)
            try:
                root = ET.fromstring(text)
            except ET.ParseError as exc:
                raise SourceError(f"{url}: malformed RSS ({exc})") from exc

            for item in root.iterfind(".//item"):
                title = (item.findtext("title") or "").strip()
                if not title:
                    continue

                # WWR writes "<company>: <role>" into the title and has no
                # separate company element.
                company, _, role = title.partition(":")
                if role.strip():
                    company, title = company.strip(), role.strip()
                else:
                    company = ""

                jobs.append(
                    Job(
                        source=self.name,
                        title=title,
                        company=company,
                        url=(item.findtext("link") or "").strip(),
                        location=(item.findtext("region") or "Remote").strip(),
                        description=item.findtext("description") or "",
                        tags=[category.replace("remote-", "").replace("-jobs", "")],
                        posted_at=ts(item.findtext("pubDate")),
                        remote=True,
                    )
                )

        return jobs
