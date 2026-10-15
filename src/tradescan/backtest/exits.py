"""Exit rules: at every close of an open trade, each rule names the orders it wants for the next bar.

A rule can ask for a stop order, a target (limit) order and/or an exit at the next open. Combined, the
tightest stop, the nearest target and the first exit at the open apply. A rule computes what all
trades share once per run (`prepare`) and keeps any per-trade state in the tracker it starts for each
trade. New rules plug in with `@exit_rules.register`.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd

from tradescan.backtest.base import ExitReason
from tradescan.backtest.rules import Bars, Rule, RuleRegistry
from tradescan.params import param
from tradescan.signals.base import Direction


@dataclass(frozen=True)
class OpenTrade:
    """A filled entry, as the exit rules see it."""

    direction: Direction
    entry_index: int  # bar of the fill
    entry_price: float
    reference: float  # the price the initial stop and the target are measured from
    stop: float  # the initial stop
    risk: float  # risk per share at the initial stop


@dataclass(frozen=True)
class ExitOrders:
    """Orders for the next bar. Levels are prices or None; `at_open` is the reason to exit at the next open."""

    stop: float | None = None
    target: float | None = None
    at_open: str | None = None
    stop_reason: str = ExitReason.STOP
    target_reason: str = ExitReason.TARGET


NO_ORDERS = ExitOrders()


class ExitTracker(Protocol):
    def orders(self, index: int) -> ExitOrders:
        """Called at the close of every bar from the entry bar on, in order, until the trade closes."""
        ...


TrackerFactory = Callable[[OpenTrade], ExitTracker]


class ExitRule(Rule):
    @abstractmethod
    def prepare(self, bars: Bars, direction: Direction) -> TrackerFactory:
        """Compute what every trade shares once per run; the result starts a tracker for each trade."""


@dataclass(frozen=True)
class FixedOrders:
    """A tracker whose orders never change."""

    fixed: ExitOrders

    def orders(self, index: int) -> ExitOrders:
        return self.fixed


@dataclass(frozen=True)
class CombinedExits:
    """Several trackers as one: the tightest stop, the nearest target and the first exit at the open win.

    Every tracker sees every close, so trackers with state (a ratcheting stop) stay in step.
    """

    direction: Direction
    trackers: tuple[ExitTracker, ...]

    def orders(self, index: int) -> ExitOrders:
        sign = self.direction.sign
        stop: tuple[float, str] | None = None  # (level, reason)
        target: tuple[float, str] | None = None
        at_open: str | None = None
        for tracker in self.trackers:
            orders = tracker.orders(index)
            if orders.stop is not None and (stop is None or sign * orders.stop > sign * stop[0]):
                stop = (orders.stop, orders.stop_reason)
            if orders.target is not None and (target is None or sign * orders.target < sign * target[0]):
                target = (orders.target, orders.target_reason)
            at_open = at_open or orders.at_open
        return ExitOrders(
            stop=stop[0] if stop else None,
            stop_reason=stop[1] if stop else ExitReason.STOP,
            target=target[0] if target else None,
            target_reason=target[1] if target else ExitReason.TARGET,
            at_open=at_open,
        )


exit_rules: RuleRegistry[ExitRule] = RuleRegistry("exit")


@exit_rules.register
@dataclass(frozen=True)
class TargetExit(ExitRule):
    target_r: float = param(
        2.0, minimum=0.25, maximum=50.0, step=0.25, label="Distance", unit="R",
        help="From the entry reference, as a multiple of the initial risk",
    )
    name = "target"
    label = "Profit target"
    description = "Limit order {target_r:g}R from the entry reference"

    def prepare(self, bars: Bars, direction: Direction) -> TrackerFactory:
        def track(trade: OpenTrade) -> ExitTracker:
            return FixedOrders(ExitOrders(target=trade.reference + trade.direction.sign * self.target_r * trade.risk))

        return track


@exit_rules.register
@dataclass(frozen=True)
class TimeExit(ExitRule):
    max_hold_bars: int = param(
        20, minimum=1, maximum=1000, step=1, label="Hold for", unit="bars", help="Counted from the entry bar"
    )
    name = "time"
    label = "Time exit"
    description = "Exit at the open {max_hold_bars} bars after the entry bar"

    def prepare(self, bars: Bars, direction: Direction) -> TrackerFactory:
        return lambda trade: _TimeLimit(trade.entry_index + self.max_hold_bars)


@dataclass(frozen=True)
class _TimeLimit:
    exit_index: int  # the bar whose open closes the trade

    def orders(self, index: int) -> ExitOrders:
        return ExitOrders(at_open=ExitReason.TIME) if index + 1 >= self.exit_index else NO_ORDERS


class _Ratchet(ABC):
    """A stop that only tightens: at every close it moves to the level the rule asks for, if that is tighter.

    The exit reason is the rule's name. Until the rule asks for a finite level the tracker places no stop.
    """

    def __init__(self, sign: float, reason: str) -> None:
        self._sign, self._reason = sign, reason
        self._level: float | None = None

    def orders(self, index: int) -> ExitOrders:
        candidate = self._candidate(index)
        if math.isfinite(candidate) and (self._level is None or self._sign * (candidate - self._level) > 0):
            self._level = candidate
        return NO_ORDERS if self._level is None else ExitOrders(stop=self._level, stop_reason=self._reason)

    @abstractmethod
    def _candidate(self, index: int) -> float:
        """The stop level the close of bar `index` asks for; NaN for none."""


class _BestPrice:
    """The highest high (lowest low for shorts) from the entry bar up to the current close."""

    def __init__(self, prices: np.ndarray, sign: float) -> None:
        self._prices, self._sign = prices, sign
        self.value = math.nan

    def update(self, index: int) -> float:
        price = float(self._prices[index])
        if math.isnan(self.value) or self._sign * (price - self.value) > 0:
            self.value = price
        return self.value


def _best_prices(bars: Bars, direction: Direction) -> np.ndarray:
    return bars.high if direction is Direction.LONG else bars.low


@exit_rules.register
@dataclass(frozen=True)
class TrailingStop(ExitRule):
    atr_mult: float = param(
        3.0, minimum=0.5, maximum=20.0, step=0.25, label="Distance", unit="ATR",
        help="From the highest high since the entry bar (the lowest low for shorts), in ATRs of the current bar",
    )
    name = "trailing"
    label = "Trailing stop"
    description = (
        "Stop {atr_mult:g} ATR below the highest high since the entry bar (above the lowest low for shorts), "
        "only tightening"
    )

    def prepare(self, bars: Bars, direction: Direction) -> TrackerFactory:
        distance = direction.sign * self.atr_mult * bars.atr
        prices = _best_prices(bars, direction)
        return lambda trade: _Trailing(_BestPrice(prices, direction.sign), distance, direction.sign, self.name)


class _Trailing(_Ratchet):
    def __init__(self, best: _BestPrice, distance: np.ndarray, sign: float, reason: str) -> None:
        super().__init__(sign, reason)
        self._best, self._distance = best, distance

    def _candidate(self, index: int) -> float:
        return self._best.update(index) - float(self._distance[index])


@exit_rules.register
@dataclass(frozen=True)
class ChannelStop(ExitRule):
    period: int = param(
        10, minimum=2, maximum=250, step=1, label="Lookback", unit="bars",
        help="The current bar and the ones before it, bars before the entry included",
    )
    name = "channel"
    label = "Channel stop"
    description = "Stop at the lowest low of the last {period} bars (the highest high for shorts), only tightening"

    def prepare(self, bars: Bars, direction: Direction) -> TrackerFactory:
        window = pd.Series(bars.low if direction is Direction.LONG else bars.high).rolling(self.period, min_periods=1)
        channel = (window.min() if direction is Direction.LONG else window.max()).to_numpy(dtype=float)
        return lambda trade: _Channel(channel, direction.sign, self.name)


class _Channel(_Ratchet):
    def __init__(self, channel: np.ndarray, sign: float, reason: str) -> None:
        super().__init__(sign, reason)
        self._channel = channel

    def _candidate(self, index: int) -> float:
        return float(self._channel[index])


@exit_rules.register
@dataclass(frozen=True)
class BreakevenStop(ExitRule):
    trigger_r: float = param(
        1.0, minimum=0.25, maximum=20.0, step=0.25, label="Trigger", unit="R",
        help="Gain from the fill price that the high since the entry bar (the low for shorts) has to reach",
    )
    lock_r: float = param(
        0.0, minimum=0.0, maximum=10.0, step=0.05, label="Lock in", unit="R",
        help="Where the stop moves, measured from the fill price; below the trigger",
    )
    name = "breakeven"
    label = "Breakeven stop"
    description = "Once the gain reaches {trigger_r:g}R from the fill, stop at {lock_r:g}R from the fill"

    def __post_init__(self) -> None:
        if self.lock_r >= self.trigger_r:
            raise ValueError(
                f"{self.name}: the locked-in gain ({self.lock_r:g}R) must be below the trigger ({self.trigger_r:g}R)"
            )

    def prepare(self, bars: Bars, direction: Direction) -> TrackerFactory:
        prices = _best_prices(bars, direction)

        def track(trade: OpenTrade) -> ExitTracker:
            sign = trade.direction.sign
            trigger = trade.entry_price + sign * self.trigger_r * trade.risk
            lock = trade.entry_price + sign * self.lock_r * trade.risk
            return _Breakeven(_BestPrice(prices, sign), trigger, lock, sign, self.name)

        return track


class _Breakeven(_Ratchet):
    def __init__(self, best: _BestPrice, trigger: float, lock: float, sign: float, reason: str) -> None:
        super().__init__(sign, reason)
        self._best, self._trigger, self._lock = best, trigger, lock

    def _candidate(self, index: int) -> float:
        return self._lock if self._sign * (self._best.update(index) - self._trigger) >= 0 else math.nan
