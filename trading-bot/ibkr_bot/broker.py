"""Market data and order helpers around ib_async."""

import logging

import pandas as pd
from ib_async import IB, MarketOrder, Stock, Trade, util

from .config import Settings

log = logging.getLogger(__name__)


def qualify_stock(ib: IB, settings: Settings) -> Stock:
    """Resolve the contract with IBKR. Fails loudly if the symbol is wrong —
    an unqualified contract is a classic silent-failure source."""
    contract = Stock(settings.symbol, settings.exchange, settings.currency)
    qualified = ib.qualifyContracts(contract)
    if not qualified:
        raise ValueError(
            f"IBKR could not resolve contract {settings.symbol} "
            f"{settings.exchange}/{settings.currency}. Check the symbol."
        )
    return qualified[0]


def fetch_bars(ib: IB, contract: Stock, bar_size: str, duration: str = "2 D") -> pd.DataFrame:
    """Historical bars as a DataFrame (oldest first).

    Uses delayed-capable historical data, which works WITHOUT paid
    market-data subscriptions — the usual fix for errors 354/10089
    that kill first-time bots requesting real-time ticks.
    """
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=duration,
        barSizeSetting=bar_size,
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
    )
    if not bars:
        raise RuntimeError(
            f"No historical data returned for {contract.symbol}. If you saw "
            "error 162/354, your account lacks a market-data subscription for "
            "this exchange; try another symbol or enable delayed data."
        )
    return util.df(bars)


def current_position(ib: IB, contract: Stock) -> int:
    for pos in ib.positions():
        if pos.contract.conId == contract.conId:
            return int(pos.position)
    return 0


def place_market_order(
    ib: IB, contract: Stock, action: str, quantity: int, dry_run: bool
) -> Trade | None:
    if dry_run:
        log.info("[DRY RUN] Would place %s %d %s (set BOT_LIVE=1 to transmit)",
                 action, quantity, contract.symbol)
        return None

    trade = ib.placeOrder(contract, MarketOrder(action, quantity))
    # Wait briefly for an ack so rejections surface here, not silently later.
    ib.sleep(2)
    status = trade.orderStatus.status
    if trade.log and status in ("Inactive", "Cancelled", "ApiCancelled"):
        reasons = "; ".join(e.message for e in trade.log if e.message)
        raise RuntimeError(
            f"Order {action} {quantity} {contract.symbol} rejected: {reasons}. "
            "If the message mentions read-only, untick 'Read-Only API' in "
            "TWS Global Configuration > API > Settings."
        )
    log.info("Order %s %d %s status: %s", action, quantity, contract.symbol, status)
    return trade
