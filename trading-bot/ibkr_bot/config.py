"""Bot configuration.

Every value can be overridden with an environment variable so the same
code runs against TWS paper, TWS live, or IB Gateway without edits.

Standard IBKR API ports:
    7497  TWS, paper trading
    7496  TWS, live trading
    4002  IB Gateway, paper trading
    4001  IB Gateway, live trading
"""

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    host: str = os.environ.get("IBKR_HOST", "127.0.0.1")
    port: int = int(os.environ.get("IBKR_PORT", "7497"))  # paper by default
    client_id: int = int(os.environ.get("IBKR_CLIENT_ID", "17"))
    connect_timeout: float = float(os.environ.get("IBKR_CONNECT_TIMEOUT", "15"))
    connect_retries: int = int(os.environ.get("IBKR_CONNECT_RETRIES", "3"))

    # Strategy
    symbol: str = os.environ.get("BOT_SYMBOL", "AAPL")
    exchange: str = os.environ.get("BOT_EXCHANGE", "SMART")
    currency: str = os.environ.get("BOT_CURRENCY", "USD")
    fast_sma: int = int(os.environ.get("BOT_FAST_SMA", "9"))
    slow_sma: int = int(os.environ.get("BOT_SLOW_SMA", "21"))
    quantity: int = int(os.environ.get("BOT_QUANTITY", "10"))
    bar_size: str = os.environ.get("BOT_BAR_SIZE", "5 mins")
    poll_seconds: int = int(os.environ.get("BOT_POLL_SECONDS", "60"))

    # Safety: orders are only transmitted when BOT_LIVE=1 is set explicitly.
    dry_run: bool = field(
        default_factory=lambda: os.environ.get("BOT_LIVE", "0") != "1"
    )

    @property
    def is_paper_port(self) -> bool:
        return self.port in (7497, 4002)


settings = Settings()
