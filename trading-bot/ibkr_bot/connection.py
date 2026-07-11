"""Robust connection handling for the IBKR API.

The two failure modes look identical from a naive `ib.connect()` call but
have completely different fixes, so we distinguish them explicitly:

* ConnectionRefusedError — nothing is listening on host:port.
  TWS/Gateway is not running, or you are pointing at the wrong port.

* TimeoutError during the handshake — the socket opened but TWS never
  completed the API handshake. This means the API is disabled in TWS
  ("Enable ActiveX and Socket Clients" unchecked), the machine is not in
  the Trusted IPs list, or another client is already using this clientId.
"""

import logging
import socket

from ib_async import IB

from .config import Settings

log = logging.getLogger(__name__)

PORT_HINTS = {
    7497: "TWS paper",
    7496: "TWS live",
    4002: "IB Gateway paper",
    4001: "IB Gateway live",
}


def port_is_open(host: str, port: int, timeout: float = 3.0) -> bool:
    """Cheap TCP probe, used to give a precise error before the API attempt."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def connect(settings: Settings) -> IB:
    """Connect to TWS/IB Gateway with retries and actionable errors."""
    if not port_is_open(settings.host, settings.port):
        listening = [p for p in PORT_HINTS if port_is_open(settings.host, p)]
        msg = (
            f"Nothing is listening on {settings.host}:{settings.port} "
            f"({PORT_HINTS.get(settings.port, 'non-standard port')}). "
        )
        if listening:
            hints = ", ".join(f"{p} ({PORT_HINTS[p]})" for p in listening)
            msg += f"However, these API ports ARE open: {hints}. Set IBKR_PORT accordingly."
        else:
            msg += (
                "No standard IBKR API port is open. Start TWS or IB Gateway, "
                "log in, and verify the Socket Port in "
                "Global Configuration > API > Settings."
            )
        raise ConnectionError(msg)

    ib = IB()
    last_error: Exception | None = None
    for attempt in range(1, settings.connect_retries + 1):
        try:
            ib.connect(
                settings.host,
                settings.port,
                clientId=settings.client_id + attempt - 1,  # dodge clientId clashes
                timeout=settings.connect_timeout,
            )
            server_time = ib.reqCurrentTime()
            accounts = ib.managedAccounts()
            log.info(
                "Connected to %s:%s (clientId=%s). Server time %s, accounts %s",
                settings.host, settings.port, ib.client.clientId,
                server_time, accounts,
            )
            return ib
        except (TimeoutError, ConnectionError, OSError) as exc:
            last_error = exc
            log.warning("Connect attempt %d/%d failed: %s",
                        attempt, settings.connect_retries, exc)

    raise ConnectionError(
        f"Port {settings.port} is open but the API handshake failed "
        f"({last_error!r}). In TWS/Gateway check Global Configuration > API > "
        "Settings: 'Enable ActiveX and Socket Clients' must be ticked, this "
        "machine must be in Trusted IPs (or use 127.0.0.1 locally), and no "
        "other program may already be connected with the same clientId."
    )
