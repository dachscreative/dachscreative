"""Entry point: python -m ibkr_bot.main

Connects to TWS/IB Gateway, then loops: fetch bars -> evaluate SMA
crossover -> place order on a signal. Dry-run by default; set BOT_LIVE=1
to actually transmit orders (use the paper port 7497/4002 first!).
"""

import logging

from .broker import current_position, fetch_bars, place_market_order, qualify_stock
from .config import settings
from .connection import connect
from .strategy import Signal, SmaCrossover

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("ibkr_bot")


def run() -> None:
    if not settings.dry_run and not settings.is_paper_port:
        log.warning("LIVE trading on a LIVE port (%s). Ctrl-C now if unintended.",
                    settings.port)

    ib = connect(settings)
    # Delayed data keeps everything working without paid subscriptions.
    ib.reqMarketDataType(3)

    contract = qualify_stock(ib, settings)
    strategy = SmaCrossover(fast=settings.fast_sma, slow=settings.slow_sma)
    log.info("Running %s on %s every %ss (dry_run=%s)",
             strategy, contract.symbol, settings.poll_seconds, settings.dry_run)

    try:
        while True:
            bars = fetch_bars(ib, contract, settings.bar_size)
            signal = strategy.evaluate(bars)
            position = current_position(ib, contract)
            log.info("close=%.2f signal=%s position=%d",
                     bars["close"].iloc[-1], signal.value, position)

            if signal is Signal.BUY and position <= 0:
                place_market_order(ib, contract, "BUY", settings.quantity,
                                   settings.dry_run)
            elif signal is Signal.SELL and position > 0:
                place_market_order(ib, contract, "SELL", position,
                                   settings.dry_run)

            ib.sleep(settings.poll_seconds)  # keeps the event loop serviced
    except KeyboardInterrupt:
        log.info("Stopping.")
    finally:
        ib.disconnect()


if __name__ == "__main__":
    run()
