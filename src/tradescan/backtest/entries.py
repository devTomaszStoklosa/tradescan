"""Entry rules: the order a signal places, and the price its initial stop and target are measured from.

New rules plug in with `@entry_rules.register`. They reuse the three order types both engines execute.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from tradescan.backtest.rules import Bars, Rule, RuleRegistry
from tradescan.params import param
from tradescan.signals.base import Direction


class OrderType(StrEnum):
    MARKET = "market"  # fills at the next open
    STOP = "stop"  # fills when price reaches the level from the near side; a gap through it fills at the open
    LIMIT = "limit"  # fills at the level or better; a gap through it fills at the open


@dataclass(frozen=True, eq=False)
class EntryOrders:
    """The entry order a signal at the close of each bar would place, for every bar at once.

    `level` is the order price (NaN for market orders) and `reference` the price the initial stop and the
    target are measured from. The order is active on the `valid_bars` bars after the signal bar.
    """

    type: OrderType
    level: np.ndarray
    reference: np.ndarray
    valid_bars: int


class EntryRule(Rule):
    @abstractmethod
    def orders(self, bars: Bars, direction: Direction) -> EntryOrders:
        """Causal: the order for bar t uses data up to and including bar t only."""


entry_rules: RuleRegistry[EntryRule] = RuleRegistry("entry")


@entry_rules.register
@dataclass(frozen=True)
class NextOpenEntry(EntryRule):
    name = "next_open"
    label = "Next open"
    description = "Market order at the next open; stop and target are measured from the signal bar's close"

    def orders(self, bars: Bars, direction: Direction) -> EntryOrders:
        return EntryOrders(OrderType.MARKET, np.full(len(bars), np.nan), bars.close, valid_bars=1)


@entry_rules.register
@dataclass(frozen=True)
class StopEntry(EntryRule):
    offset_atr: float = param(
        0.0, minimum=0.0, maximum=5.0, step=0.05, label="Offset", unit="ATR",
        help="Above the signal bar's high for longs, below its low for shorts",
    )
    valid_bars: int = param(
        1, minimum=1, maximum=20, step=1, label="Active for", unit="bars",
        help="Bars after the signal bar before an unfilled order is cancelled",
    )
    name = "stop"
    label = "Stop order"
    description = (
        "Buy-stop {offset_atr:g} ATR above the signal bar's high (sell-stop below its low for shorts), "
        "active for {valid_bars} bar(s)"
    )

    def orders(self, bars: Bars, direction: Direction) -> EntryOrders:
        anchor = bars.high if direction is Direction.LONG else bars.low
        level = anchor + direction.sign * self.offset_atr * bars.atr
        return EntryOrders(OrderType.STOP, level, level, self.valid_bars)


@entry_rules.register
@dataclass(frozen=True)
class LimitEntry(EntryRule):
    offset_atr: float = param(
        0.5, minimum=0.0, maximum=5.0, step=0.05, label="Offset", unit="ATR",
        help="Below the signal bar's close for longs, above it for shorts",
    )
    valid_bars: int = param(
        1, minimum=1, maximum=20, step=1, label="Active for", unit="bars",
        help="Bars after the signal bar before an unfilled order is cancelled",
    )
    name = "limit"
    label = "Limit order"
    description = (
        "Buy-limit {offset_atr:g} ATR below the signal bar's close (sell-limit above it for shorts), "
        "active for {valid_bars} bar(s)"
    )

    def orders(self, bars: Bars, direction: Direction) -> EntryOrders:
        level = bars.close - direction.sign * self.offset_atr * bars.atr
        return EntryOrders(OrderType.LIMIT, level, level, self.valid_bars)
