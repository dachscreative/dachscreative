"""Shared source machinery."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Iterable

import requests

from ..models import Job


class SourceError(Exception):
    """A source failed. One failing source must not abort the whole run."""


class Source:
    name = "base"

    def __init__(self, options: dict[str, Any], timeout: float, delay: float, user_agent: str):
        self.options = options
        self.timeout = timeout
        self.delay = delay
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "*/*"})

    def fetch(self) -> Iterable[Job]:  # pragma: no cover - interface
        raise NotImplementedError

    # -- helpers ------------------------------------------------------------

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        # Be a polite client: one request, then wait. These are free public
        # endpoints and hammering them is how they stop being free and public.
        time.sleep(self.delay)
        try:
            resp = self.session.get(url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise SourceError(f"{url}: {exc}") from exc
        if resp.status_code == 429:
            raise SourceError(f"{url}: rate limited (429)")
        if not resp.ok:
            raise SourceError(f"{url}: HTTP {resp.status_code}")
        return resp

    def get_json(self, url: str, **kwargs: Any) -> Any:
        resp = self._get(url, **kwargs)
        try:
            return resp.json()
        except ValueError as exc:
            raise SourceError(f"{url}: response was not JSON") from exc

    def get_text(self, url: str, **kwargs: Any) -> str:
        return self._get(url, **kwargs).text


def ts(value: Any) -> datetime | None:
    """Best-effort timestamp parsing across the formats these feeds use."""
    if value in (None, "", 0):
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()

    # ISO 8601, with or without a trailing Z.
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # RFC 822, as used by RSS.
    try:
        from email.utils import parsedate_to_datetime

        parsed = parsedate_to_datetime(text)
        if parsed:
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass

    # A bare epoch delivered as a string.
    if text.isdigit():
        return ts(int(text))

    return None
