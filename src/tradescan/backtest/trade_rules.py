"""The trade rules of one backtest: an entry rule, plus exit rules on top of the initial ATR stop.

Both engines prepare the rules once per run and ask the result the same questions: which order a
signal places (`plan`) and which exit orders an open trade has (`track`). Only the order execution
differs between them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from tradescan.backtest.base import BacktestConfig
from tradescan.backtest.entries import EntryOrders, EntryRule, NextOpenEntry, OrderType, entry_rules
from tradescan.backtest.exits import (
    CombinedExits,
    ExitOrders,
    ExitRule,
    ExitTracker,
    FixedOrders,
    OpenTrade,
    TargetExit,
    TimeExit,
    TrackerFactory,
    exit_rules,
)
from tradescan.backtest.rules import Bars, RuleRegistry
from tradescan.params import Overrides
from tradescan.risk import position_size, trade_levels
from tradescan.signals.base import Direction


@dataclass(frozen=True)
class TradeRules:
    """The default reproduces the original rules: next-open entry, 2R target, 20-bar time exit."""

    entry: EntryRule = field(default_factory=NextOpenEntry)
    exits: tuple[ExitRule, ...] = field(default_factory=lambda: (TargetExit(), TimeExit()))

    def __post_init__(self) -> None:
        names = [rule.name for rule in self.exits]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise ValueError(f"Exit rule(s) given more than once: {', '.join(repeated)}")

    def prepare(self, bars: Bars, direction: Direction) -> PreparedRules:
        return PreparedRules(
            bars=bars,
            direction=direction,
            entry=self.entry.orders(bars, direction),
            exits=tuple(rule.prepare(bars, direction) for rule in self.exits),
        )


@dataclass(frozen=True)
class EntryPlan:
    """The entry order a signal places, sized from the initial stop."""

    type: OrderType
    level: float  # NaN for market orders
    reference: float
    stop: float
    risk: float  # per share
    size: float
    valid_bars: int


@dataclass(frozen=True, eq=False)
class PreparedRules:
    bars: Bars
    direction: Direction
    entry: EntryOrders
    exits: tuple[TrackerFactory, ...]

    def plan(self, index: int, equity: float, config: BacktestConfig) -> EntryPlan | None:
        """The order a signal at the close of bar `index` places; None when it has no price or size."""
        reference = float(self.entry.reference[index])
        level = float(self.entry.level[index])
        atr = float(self.bars.atr[index])
        needs_level = self.entry.type is not OrderType.MARKET
        if not (np.isfinite(atr) and np.isfinite(reference)) or (needs_level and not np.isfinite(level)):
            return None
        stop, _, risk = trade_levels(self.direction, reference, atr, config.atr_mult, ())
        size = position_size(equity, reference, risk, config.risk_pct, config.max_position_pct, config.lot_size)
        if size <= 0:
            return None
        return EntryPlan(self.entry.type, level, reference, stop, risk, size, self.entry.valid_bars)

    def track(self, trade: OpenTrade) -> ExitTracker:
        """The exit orders of one trade: the initial stop plus every exit rule."""
        initial = FixedOrders(ExitOrders(stop=trade.stop))
        return CombinedExits(self.direction, (initial, *(start(trade) for start in self.exits)))


@dataclass(frozen=True)
class RuleChoice:
    """A rule by name with per-run parameter overrides."""

    name: str
    params: Overrides = field(default_factory=dict)


@dataclass(frozen=True)
class RuleCatalog:
    """The rules a backtest can choose from, and the ones used when a request names none."""

    entries: RuleRegistry[EntryRule] = entry_rules
    exits: RuleRegistry[ExitRule] = exit_rules
    default_entry: str = NextOpenEntry.name
    default_exits: tuple[str, ...] = (TargetExit.name, TimeExit.name)

    def build(self, entry: RuleChoice | None = None, exits: Sequence[RuleChoice] | None = None) -> TradeRules:
        """Rules with validated parameters. No exits given means the defaults; an empty list keeps only the stop."""
        entry_choice = entry or RuleChoice(self.default_entry)
        exit_choices = exits if exits is not None else [RuleChoice(name) for name in self.default_exits]
        return TradeRules(
            entry=self.entries.create(entry_choice.name, entry_choice.params),
            exits=tuple(self.exits.create(choice.name, choice.params) for choice in exit_choices),
        )


default_catalog = RuleCatalog()
