"""Shared backtest types. Both engines follow the same trade rules:

* a signal on bar t enters at the open of bar t+1 (market order),
* stop and target come from `risk.trade_levels` around the signal bar's close and ATR,
* stop/target are checked from the bar after the entry bar (backtrader bracket semantics),
  the stop wins when both are touched on the same bar,
* a time exit fills at the open `max_hold_bars` bars after entry,
* size comes from `risk.position_size` using equity at the signal bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from tradescan.signals.base import Direction, Signal


@dataclass(frozen=True)
class BacktestConfig:
    initial_equity: float = 100_000.0
    risk_pct: float = 1.0
    max_position_pct: float = 25.0
    lot_size: float = 1.0
    atr_period: int = 14
    atr_mult: float = 2.0
    target_r: float = 2.0
    max_hold_bars: int = 20
    commission_pct: float = 0.1
    slippage_pct: float = 0.05
    bars_per_year: int = 252


class ExitReason:
    STOP = "stop"
    TARGET = "target"
    TIME = "time"
    OPEN = "open"  # still open on the last bar, marked to the last close


@dataclass(frozen=True)
class Trade:
    direction: Direction
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    size: float
    pnl: float  # net of commissions
    r_multiple: float  # pnl / planned risk
    exit_reason: str

    @property
    def is_closed(self) -> bool:
        return self.exit_reason != ExitReason.OPEN


@dataclass(frozen=True)
class BacktestResult:
    engine: str
    ticker: str
    signal: str
    equity: pd.Series
    trades: tuple[Trade, ...]


class BacktestEngine(Protocol):
    name: str

    def run(self, ticker: str, df: pd.DataFrame, signal: Signal, config: BacktestConfig) -> BacktestResult: ...
