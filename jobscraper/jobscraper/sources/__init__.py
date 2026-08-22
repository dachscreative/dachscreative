"""Source registry."""

from __future__ import annotations

from typing import Any

from .arbeitnow import Arbeitnow
from .base import Source, SourceError
from .greenhouse import Greenhouse
from .remoteok import RemoteOK
from .weworkremotely import WeWorkRemotely

REGISTRY: dict[str, type[Source]] = {
    cls.name: cls for cls in (RemoteOK, Arbeitnow, WeWorkRemotely, Greenhouse)
}

__all__ = ["REGISTRY", "Source", "SourceError", "build"]


def build(spec: dict[str, Any], timeout: float, delay: float, user_agent: str) -> Source:
    name = str(spec.get("name", "")).lower()
    if name not in REGISTRY:
        known = ", ".join(sorted(REGISTRY))
        raise SourceError(f"unknown source {name!r} (known: {known})")
    options = {k: v for k, v in spec.items() if k not in ("name", "enabled")}
    return REGISTRY[name](options, timeout, delay, user_agent)
