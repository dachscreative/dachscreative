"""Simple SMA-crossover signal on historical bars.

Deliberately minimal: the point of this repo is a *working API layer*;
swap this module out for your real strategy.
"""

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class SmaCrossover:
    fast: int = 9
    slow: int = 21

    def evaluate(self, bars: pd.DataFrame) -> Signal:
        """bars must have a 'close' column, oldest row first."""
        if len(bars) < self.slow + 1:
            return Signal.HOLD

        close = bars["close"]
        fast = close.rolling(self.fast).mean()
        slow = close.rolling(self.slow).mean()

        crossed_up = fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1]
        crossed_down = fast.iloc[-2] >= slow.iloc[-2] and fast.iloc[-1] < slow.iloc[-1]

        if crossed_up:
            return Signal.BUY
        if crossed_down:
            return Signal.SELL
        return Signal.HOLD
