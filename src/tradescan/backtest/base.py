"""Shared backtest types. Both engines execute the same trade rules (`trade_rules.TradeRules`):

* a signal on bar t places the entry rule's order: a market order for the open of bar t+1, or a stop
  or limit order active on the next `valid_bars` bars; signals are ignored while an order waits or a
  position is open, and so are signals on bars where an entry filter blocks them,
* the initial stop sits `atr_mult` ATRs (of the signal bar) from the entry rule's reference price, and
  size comes from `risk.position_size` using equity at the signal bar,
* exit orders are placed on the entry bar and checked from the next bar (backtrader bracket
  semantics); exit rules can move them at every close or ask to exit at the next open,
* on a bar that touches both, the stop wins over the target; a gap through a level fills at the open,
* fill prices follow backtrader's percentage slippage, which never moves a fill outside the bar,
* with pyramiding (`max_units` above 1) a position adds units by stop orders `add_every_atr` ATRs apart and
  moves its stop with every add (see `pyramid`); on a bar where the position exits, no unit is added.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import pandas as pd

from tradescan.signals.base import Direction, Signal

if TYPE_CHECKING:
    from tradescan.backtest.trade_rules import TradeRules


@dataclass(frozen=True)
class BacktestConfig:
    initial_equity: float = 100_000.0
    risk_pct: float = 1.0
    max_position_pct: float = 25.0
    lot_size: float = 1.0
    atr_period: int = 14
    atr_mult: float = 2.0
    commission_pct: float = 0.1
    slippage_pct: float = 0.05
    bars_per_year: int = 252
    oos_pct: float = 30.0  # the last part of the history, reported separately (see `oos`)
    max_units: int = 1  # the first entry plus the adds; 1 is no pyramiding (see `pyramid`)
    add_every_atr: float = 0.5  # distance between units, in ATRs of the signal bar


class ExitReason:
    STOP = "stop"
    TARGET = "target"
    TIME = "time"
    OPEN = "open"  # still open on the last bar, marked to the last close
    REBALANCE = "rebalance"  # sold out by a rotation's rebalance


@dataclass(frozen=True)
class Fill:
    date: pd.Timestamp
    price: float


@dataclass(frozen=True)
class Trade:
    """One position. With pyramiding it holds every unit: `entry_date` is the first unit's fill, `entry_price`
    the average fill of the units, `size` and `pnl` all units', and `adds` the fills after the first."""

    direction: Direction
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    size: float
    pnl: float  # net of commissions
    r_multiple: float  # pnl / planned risk (of one unit)
    exit_reason: str
    adds: tuple[Fill, ...] = ()

    @property
    def units(self) -> int:
        return 1 + len(self.adds)

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

    def run(
        self, ticker: str, df: pd.DataFrame, signal: Signal, config: BacktestConfig, rules: TradeRules | None = None
    ) -> BacktestResult:
        """`rules` defaults to `TradeRules()`, the original next-open entry with a target and a time exit."""
        ...
