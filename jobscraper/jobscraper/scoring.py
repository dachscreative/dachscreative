"""Keyword scoring.

A posting's score is the sum of the weights of the include terms it contains,
with title matches multiplied, exclude terms subtracted, and a bonus for being
recent. Anything scoring below scoring.min_score is dropped.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .config import ScoringConfig
from .models import Job


def _term_pattern(term: str) -> re.Pattern[str]:
    # Word-boundary match so "go" does not fire on "django" and "r" does not
    # fire on every posting ever written.
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)


class Scorer:
    def __init__(self, cfg: ScoringConfig):
        self.cfg = cfg
        self._include = [(t, w, _term_pattern(t)) for t, w in cfg.include.items()]
        self._exclude = [(t, w, _term_pattern(t)) for t, w in cfg.exclude.items()]

    def score(self, job: Job) -> tuple[float, list[str]]:
        title = job.title or ""
        body = f"{job.description or ''} {' '.join(job.tags)}"

        total = 0.0
        matched: list[str] = []

        for term, weight, pattern in self._include:
            in_title = bool(pattern.search(title))
            in_body = bool(pattern.search(body))
            if in_title:
                total += weight * self.cfg.title_multiplier
                matched.append(f"{term}(title)")
            elif in_body:
                total += weight
                matched.append(term)

        for term, weight, pattern in self._exclude:
            if pattern.search(title) or pattern.search(body):
                # Weights in [scoring.exclude] are written as negative numbers,
                # but tolerate a positive one meaning the same thing.
                total -= abs(weight)
                matched.append(f"-{term}")

        if job.posted_at and self.cfg.recency_bonus:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.cfg.recency_days)
            if job.posted_at >= cutoff:
                total += self.cfg.recency_bonus
                matched.append("recent")

        return round(total, 2), matched

    def keeps(self, score: float) -> bool:
        return score >= self.cfg.min_score
