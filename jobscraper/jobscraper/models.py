"""The one shape every source produces."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime


def _clean(text: str | None) -> str:
    if not text:
        return ""
    # Most feeds hand back HTML. Nobody wants tags in a CSV cell.
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    return re.sub(r"[ \t]+", " ", text).strip()


@dataclass
class Job:
    source: str
    title: str
    company: str
    url: str
    location: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    posted_at: datetime | None = None
    remote: bool = False

    # Filled in by the pipeline, not by sources.
    score: float = 0.0
    matched: list[str] = field(default_factory=list)
    is_new: bool = False

    def __post_init__(self) -> None:
        self.title = _clean(self.title)
        self.company = _clean(self.company)
        self.location = _clean(self.location)
        self.description = _clean(self.description)
        self.tags = [t.strip().lower() for t in self.tags if t and t.strip()]

    @property
    def uid(self) -> str:
        """Stable identity for a posting.

        The URL is the natural key, but the same job is often re-posted at a new
        URL with a fresh id in the path, so hashing company+title instead means
        a re-post is recognised rather than announced as new every day.

        Deliberately NOT keyed on source: one posting syndicated to two boards
        has to collapse to a single entry, otherwise it is exported twice and
        reported as new twice.
        """
        basis = "|".join(
            [
                self.company.lower(),
                re.sub(r"\W+", " ", self.title.lower()).strip(),
            ]
        )
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
