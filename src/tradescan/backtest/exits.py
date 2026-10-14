"""Exit rules: at every close of an open trade, each rule names the orders it wants for the next bar.

A rule can ask for a stop order, a target (limit) order and/or an exit at the next open. Combined, the
tightest stop, the nearest target and the first exit at the open apply. A rule computes what all
trades share once per run (`prepare`) and keeps any per-trade state in the tracker it starts for each
trade. New rules plug in with `@exit_rules.register`.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

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
