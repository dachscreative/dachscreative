"""The VPN kill switch.

run.sh treats exit code 2 as "aborted before scraping because the VPN check
failed". Everything here exists to make that decision correctly and to explain
itself when it says no - a kill switch that fails without saying why gets
disabled with --no-vpn-check and then never gets re-enabled.

Two independent checks, both must pass:

  1. A VPN-ish network interface is up (tun*/wg*/ppp* on Linux, utun* on macOS).
  2. The public IP is not one of the addresses listed as the bare connection.

Check 1 alone is not enough: an interface can be up while the route leaks.
Check 2 alone is not enough either - it needs a network round trip, and a
blocked_ips list that was never filled in makes it a no-op.
"""

from __future__ import annotations

import platform
import socket
from dataclasses import dataclass
from pathlib import Path

from .config import VpnConfig


@dataclass
class VpnStatus:
    ok: bool
    reason: str
    interface: str | None = None
    public_ip: str | None = None


def _linux_interfaces() -> list[str]:
    net = Path("/sys/class/net")
    if not net.is_dir():
        return []
    names = []
    for iface in sorted(net.iterdir()):
        # operstate is "up", "down", or "unknown". Point-to-point tunnels
        # frequently report "unknown" while carrying traffic, so treat only an
        # explicit "down" as down.
        state = ""
        try:
            state = (iface / "operstate").read_text().strip()
        except OSError:
            pass
        if state != "down":
            names.append(iface.name)
    return names


def _generic_interfaces() -> list[str]:
    # socket.if_nameindex is available on Linux and macOS and needs no
    # subprocess. It lists every interface, up or not, which is why the Linux
    # path above is preferred where /sys is present.
    try:
        return [name for _, name in socket.if_nameindex()]
    except (OSError, AttributeError):
        return []


def find_vpn_interface(prefixes: list[str]) -> str | None:
    names = _linux_interfaces() if platform.system() == "Linux" else []
    if not names:
        names = _generic_interfaces()
    for name in names:
        for prefix in prefixes:
            if name.startswith(prefix):
                return name
    return None


def public_ip(url: str, timeout: float, user_agent: str) -> str | None:
    try:
        import requests

        resp = requests.get(url, timeout=timeout, headers={"User-Agent": user_agent})
        resp.raise_for_status()
        return resp.text.strip()
    except Exception:
        # A failed lookup is not proof of a leak, and it is not proof of safety
        # either. The caller decides; see check() below.
        return None


def check(cfg: VpnConfig, user_agent: str) -> VpnStatus:
    iface = find_vpn_interface(cfg.interface_prefixes)

    if cfg.require_interface and iface is None:
        return VpnStatus(
            ok=False,
            reason=(
                "No VPN interface found (looked for "
                + ", ".join(p + "*" for p in cfg.interface_prefixes)
                + "). Connect the VPN, or pass --no-vpn-check to scrape without it."
            ),
        )

    ip = public_ip(cfg.check_url, cfg.timeout, user_agent)

    if ip is None:
        if cfg.blocked_ips:
            # There is a list to check against and we could not check it. With
            # a real leak-prevention requirement configured, refuse.
            return VpnStatus(
                ok=False,
                reason=(
                    f"Could not reach {cfg.check_url} to confirm the public IP, "
                    "and blocked_ips is set. Refusing to scrape rather than risk "
                    "the bare connection."
                ),
                interface=iface,
            )
        return VpnStatus(
            ok=True,
            reason=f"VPN interface {iface} is up (public IP not verified)",
            interface=iface,
        )

    if ip in cfg.blocked_ips:
        return VpnStatus(
            ok=False,
            reason=(
                f"Public IP is {ip}, which is listed in vpn.blocked_ips - "
                "traffic is going out over the bare connection."
            ),
            interface=iface,
            public_ip=ip,
        )

    where = f"interface {iface}" if iface else "no interface requirement"
    return VpnStatus(ok=True, reason=f"public IP {ip}, {where}", interface=iface, public_ip=ip)
