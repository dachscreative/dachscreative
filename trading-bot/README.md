# IBKR Trading Bot

A minimal, working Interactive Brokers trading bot built on
[`ib_async`](https://github.com/ib-api-reloaded/ib_async), with an API
connection layer that tells you *exactly* what is wrong when it can't
connect — because "the API doesn't work" is almost never the code's fault;
it's TWS configuration.

> **Why not `ib_insync`?** That library was abandoned in 2024 and its
> PyPI package is no longer maintained. `ib_async` is the community
> successor with an identical API. If an older bot imports `ib_insync`,
> that alone can break a fresh install.

## Quick start

```bash
cd trading-bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Diagnose your TWS/Gateway API setup (do this first!)
python scripts/check_connection.py

# 2. Run the bot (dry-run by default — it logs orders, never sends them)
python -m ibkr_bot.main

# 3. Go live on the PAPER account only after dry-run looks right
BOT_LIVE=1 IBKR_PORT=7497 python -m ibkr_bot.main
```

## One-time TWS / IB Gateway setup (the part that always breaks)

In TWS: **File → Global Configuration → API → Settings**

1. ✅ Tick **Enable ActiveX and Socket Clients** — *the API is OFF by default.*
2. Note the **Socket Port** and match it to `IBKR_PORT`:

   | Port | Application | Account |
   |------|-------------|---------|
   | 7497 | TWS         | Paper   |
   | 7496 | TWS         | Live    |
   | 4002 | IB Gateway  | Paper   |
   | 4001 | IB Gateway  | Live    |

3. ❌ Untick **Read-Only API** if the bot should place orders.
4. If the bot runs on a different machine: untick **Allow connections from
   localhost only** and add the bot machine's IP to **Trusted IPs**.
5. Log into the **paper** account in TWS when using port 7497/4002 —
   the port follows the login type, not the checkbox.
6. Keep TWS logged in; the API dies when TWS logs out (use IB Gateway or
   TWS's auto-restart setting for long-running bots).

## Common API errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `ConnectionRefusedError` | Nothing listening on that port | Start TWS/Gateway; check the port table above |
| Connect hangs, then `TimeoutError` | API disabled, or IP not trusted | Setup steps 1 and 4 |
| Connects then instantly disconnects | clientId already in use | Change `IBKR_CLIENT_ID` |
| Error 354 / 10089 on market data | No real-time data subscription | Bot already uses delayed data (`reqMarketDataType(3)`) and historical bars |
| Error 200 "No security definition" | Bad symbol/exchange/currency | Bot calls `qualifyContracts` and fails loudly with the details |
| Orders rejected, mention read-only | Read-Only API ticked | Setup step 3 |
| `ModuleNotFoundError: ib_insync` | Dead library | `pip install ib_async`, imports already updated here |

## Configuration

Everything is an environment variable (defaults in `ibkr_bot/config.py`):

| Variable | Default | Meaning |
|---|---|---|
| `IBKR_HOST` | `127.0.0.1` | TWS/Gateway host |
| `IBKR_PORT` | `7497` | API port (paper TWS) |
| `IBKR_CLIENT_ID` | `17` | API client id |
| `BOT_SYMBOL` | `AAPL` | Stock to trade |
| `BOT_FAST_SMA` / `BOT_SLOW_SMA` | `9` / `21` | Strategy periods |
| `BOT_QUANTITY` | `10` | Order size (shares) |
| `BOT_BAR_SIZE` | `5 mins` | Bar size for signals |
| `BOT_POLL_SECONDS` | `60` | Loop interval |
| `BOT_LIVE` | unset | Set to `1` to actually transmit orders |

## Layout

```
trading-bot/
├── ibkr_bot/
│   ├── config.py       # env-driven settings
│   ├── connection.py   # connect with retries + precise error messages
│   ├── broker.py       # contract qualification, bars, orders
│   ├── strategy.py     # SMA crossover (swap in your own)
│   └── main.py         # entry point: python -m ibkr_bot.main
└── scripts/
    └── check_connection.py  # run this when "the API doesn't work"
```

## Disclaimer

Educational example. Test on the paper account. Trading involves risk of
loss; nothing here is financial advice.
