#!/usr/bin/env python3
"""IBKR API connection doctor.

Run this FIRST whenever "the API doesn't work":

    python scripts/check_connection.py [host]

It probes all four standard ports, attempts a real API handshake on
whichever is open, and prints the exact fix for what it finds.
"""

import sys

sys.path.insert(0, ".")  # allow running from the trading-bot directory

from ibkr_bot.connection import PORT_HINTS, port_is_open  # noqa: E402

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"


def main() -> int:
    print(f"IBKR API connection check against {HOST}\n" + "=" * 50)

    open_ports = []
    for port, label in PORT_HINTS.items():
        is_open = port_is_open(HOST, port)
        print(f"  port {port:<5} ({label:<16}) : {'OPEN' if is_open else 'closed'}")
        if is_open:
            open_ports.append(port)

    if not open_ports:
        print(
            "\nRESULT: No IBKR API port is reachable.\n"
            "  1. Is TWS or IB Gateway actually running and LOGGED IN?\n"
            "  2. In TWS: File > Global Configuration > API > Settings —\n"
            "     tick 'Enable ActiveX and Socket Clients' and note the Socket Port.\n"
            "  3. If TWS runs on another machine, untick 'Allow connections\n"
            "     from localhost only' and add this machine to Trusted IPs.\n"
            "  4. Check no firewall blocks the port."
        )
        return 1

    port = open_ports[0]
    print(f"\nAttempting API handshake on port {port} ...")
    try:
        from ib_async import IB
    except ImportError:
        print(
            "RESULT: python package 'ib_async' is not installed.\n"
            "  pip install -r requirements.txt\n"
            "  (Note: the old 'ib_insync' package is dead — do not use it.)"
        )
        return 1

    ib = IB()
    try:
        ib.connect(HOST, port, clientId=991, timeout=10)
    except Exception as exc:  # noqa: BLE001 - we want to explain anything
        print(
            f"RESULT: Socket is open but the handshake failed: {exc!r}\n"
            "  Most likely causes, in order:\n"
            "  1. 'Enable ActiveX and Socket Clients' is UNTICKED in\n"
            "     Global Configuration > API > Settings.\n"
            "  2. This machine is not in the Trusted IPs list.\n"
            "  3. A popup in TWS is waiting for you to accept the connection.\n"
            "  4. clientId 991 already in use (unlikely; rerun to confirm)."
        )
        return 1

    server_time = ib.reqCurrentTime()
    accounts = ib.managedAccounts()
    paper = "PAPER" if port in (7497, 4002) else "LIVE"
    print(
        f"RESULT: SUCCESS — connected to {PORT_HINTS[port]} ({paper}).\n"
        f"  Server time : {server_time}\n"
        f"  Accounts    : {', '.join(accounts) or '(none reported)'}\n"
        f"  Use IBKR_PORT={port} when running the bot."
    )
    ib.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
