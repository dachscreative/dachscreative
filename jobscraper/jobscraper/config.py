"""Configuration loading.

The config is TOML at the project root. Everything has a default, so a missing
config.toml is a working config rather than an error - but the defaults score
nothing, and a run that matches nothing says so loudly rather than exporting an
empty file and calling it a success.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - depends on interpreter
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        raise SystemExit(
            "This python needs the 'tomli' package for TOML support.\n"
            "Run ./setup.sh, or: pip install tomli"
        )


class ConfigError(Exception):
    """Raised for a config file that exists but cannot be used."""


@dataclass
class VpnConfig:
    # Names here are prefixes. tun/wg cover OpenVPN and WireGuard on Linux;
    # utun is what macOS calls the same thing, so the check works on both.
    interface_prefixes: list[str] = field(
        default_factory=lambda: ["tun", "wg", "ppp", "utun"]
    )
    require_interface: bool = True
    # A run whose public IP is one of these is a run leaking the home address.
    blocked_ips: list[str] = field(default_factory=list)
    check_url: str = "https://api.ipify.org"
    timeout: float = 10.0


@dataclass
class ScoringConfig:
    include: dict[str, float] = field(default_factory=dict)
    exclude: dict[str, float] = field(default_factory=dict)
    title_multiplier: float = 3.0
    min_score: float = 1.0
    recency_days: int = 7
    recency_bonus: float = 1.0


@dataclass
class FilterConfig:
    posted_within_days: int = 30
    remote_only: bool = False
    locations: list[str] = field(default_factory=list)


@dataclass
class Config:
    sources: list[dict[str, Any]] = field(default_factory=list)
    vpn: VpnConfig = field(default_factory=VpnConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    request_timeout: float = 30.0
    request_delay: float = 1.0
    user_agent: str = "jobscraper/1.0 (personal job search; +contact in config)"

    @property
    def has_scoring_terms(self) -> bool:
        return bool(self.include_terms)

    @property
    def include_terms(self) -> dict[str, float]:
        return self.scoring.include


def _as_float_map(raw: Any, where: str) -> dict[str, float]:
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"[{where}] must be a table of term = weight")
    out: dict[str, float] = {}
    for term, weight in raw.items():
        if not isinstance(weight, (int, float)):
            raise ConfigError(f"[{where}] {term!r} weight must be a number, got {weight!r}")
        out[str(term).lower()] = float(weight)
    return out


def load(root: Path) -> Config:
    """Read <root>/config.toml, falling back to config.example.toml."""
    path = root / "config.toml"
    if not path.exists():
        example = root / "config.example.toml"
        if example.exists():
            path = example
        else:
            return Config()

    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path.name} is not valid TOML: {exc}") from exc

    cfg = Config()

    sources = raw.get("sources", [])
    if sources and not isinstance(sources, list):
        raise ConfigError("[[sources]] must be a list of tables")
    cfg.sources = [s for s in sources if s.get("enabled", True)]

    vpn_raw = raw.get("vpn", {})
    cfg.vpn = VpnConfig(
        interface_prefixes=list(
            vpn_raw.get("interface_prefixes", VpnConfig().interface_prefixes)
        ),
        require_interface=bool(vpn_raw.get("require_interface", True)),
        blocked_ips=[str(ip) for ip in vpn_raw.get("blocked_ips", [])],
        check_url=str(vpn_raw.get("check_url", VpnConfig().check_url)),
        timeout=float(vpn_raw.get("timeout", 10.0)),
    )

    sc_raw = raw.get("scoring", {})
    cfg.scoring = ScoringConfig(
        include=_as_float_map(sc_raw.get("include"), "scoring.include"),
        exclude=_as_float_map(sc_raw.get("exclude"), "scoring.exclude"),
        title_multiplier=float(sc_raw.get("title_multiplier", 3.0)),
        min_score=float(sc_raw.get("min_score", 1.0)),
        recency_days=int(sc_raw.get("recency_days", 7)),
        recency_bonus=float(sc_raw.get("recency_bonus", 1.0)),
    )

    f_raw = raw.get("filters", {})
    cfg.filters = FilterConfig(
        posted_within_days=int(f_raw.get("posted_within_days", 30)),
        remote_only=bool(f_raw.get("remote_only", False)),
        locations=[str(x).lower() for x in f_raw.get("locations", [])],
    )

    http = raw.get("http", {})
    cfg.request_timeout = float(http.get("timeout", 30.0))
    cfg.request_delay = float(http.get("delay", 1.0))
    cfg.user_agent = str(http.get("user_agent", cfg.user_agent))

    return cfg
