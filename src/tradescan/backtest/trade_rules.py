"""The trade rules of one backtest: entry filters, an entry rule, and exit rules on top of the initial ATR stop.

Both engines prepare the rules once per run and ask the result the same questions: which order a
signal places, if its filters allow it (`plan`), and which exit orders an open trade has (`track`).
Only the order execution differs between them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

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
from tradescan.backtest.filters import EntryFilter, FilterInputs, entry_filters
from tradescan.backtest.rules import Bars, RuleRegistry
from tradescan.params import Overrides
from tradescan.risk import position_size, trade_levels
from tradescan.signals.base import Direction


def _check_unique(rules: Sequence[ExitRule | EntryFilter], what: str) -> None:
    names = [rule.name for rule in rules]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise ValueError(f"{what} given more than once: {', '.join(repeated)}")


@dataclass(frozen=True)
class TradeRules:
    """The default reproduces the original rules: no filters, next-open entry, 2R target, 20-bar time exit.

    `benchmark_close` holds the benchmark's closes for the filters that compare the market (`needs_benchmark`);
    it is data for one run, not a parameter, so it takes no part in comparing rules.
    """

    entry: EntryRule = field(default_factory=NextOpenEntry)
    exits: tuple[ExitRule, ...] = field(default_factory=lambda: (TargetExit(), TimeExit()))
    filters: tuple[EntryFilter, ...] = ()
    benchmark_close: pd.Series | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        _check_unique(self.exits, "Exit rule(s)")
        _check_unique(self.filters, "Entry filter(s)")

    @property
    def needs_benchmark(self) -> bool:
        return any(rule.needs_benchmark for rule in self.filters)

    def with_benchmark(self, close: pd.Series | None) -> TradeRules:
        return replace(self, benchmark_close=close)

    def prepare(self, bars: Bars, direction: Direction) -> PreparedRules:
        inputs = FilterInputs(bars, self.benchmark_close)
        allowed = np.ones(len(bars), dtype=bool)
        for rule in self.filters:
            allowed &= rule.allows(inputs, direction)
        return PreparedRules(
            bars=bars,
            direction=direction,
            allowed=allowed,
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
    atr: float  # of the signal bar, which sized the order


@dataclass(frozen=True, eq=False)
class PreparedRules:
    bars: Bars
    direction: Direction
    allowed: np.ndarray  # True where every entry filter lets a signal trade
    entry: EntryOrders
    exits: tuple[TrackerFactory, ...]

    def plan(self, index: int, equity: float, config: BacktestConfig) -> EntryPlan | None:
        """The order a signal at the close of bar `index` places; None when an entry filter blocks the signal
        or it has no price or size."""
        if not self.allowed[index]:
            return None
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
        return EntryPlan(self.entry.type, level, reference, stop, risk, size, self.entry.valid_bars, atr)

    def track(self, trade: OpenTrade, extra: tuple[ExitTracker, ...] = ()) -> ExitTracker:
        """The exit orders of one trade: the initial stop plus every exit rule, and `extra` trackers such as the
        stop that pyramiding moves."""
        initial = FixedOrders(ExitOrders(stop=trade.stop))
        return CombinedExits(self.direction, (initial, *(start(trade) for start in self.exits), *extra))


@dataclass(frozen=True)
class RuleChoice:
    """A rule by name with per-run parameter overrides."""

    name: str
    params: Overrides = field(default_factory=dict)


@dataclass(frozen=True)
class RuleCatalog:
    """The rules a backtest can choose from, and the ones used when a request names none (no filters by default)."""

    entries: RuleRegistry[EntryRule] = entry_rules
    exits: RuleRegistry[ExitRule] = exit_rules
    filters: RuleRegistry[EntryFilter] = entry_filters
    default_entry: str = NextOpenEntry.name
    default_exits: tuple[str, ...] = (TargetExit.name, TimeExit.name)

    def build(
        self,
        entry: RuleChoice | None = None,
        exits: Sequence[RuleChoice] | None = None,
        filters: Sequence[RuleChoice] = (),
    ) -> TradeRules:
        """Rules with validated parameters. No exits given means the defaults; an empty list keeps only the stop."""
        entry_choice = entry or RuleChoice(self.default_entry)
        exit_choices = exits if exits is not None else [RuleChoice(name) for name in self.default_exits]
        return TradeRules(
            entry=self.entries.create(entry_choice.name, entry_choice.params),
            exits=tuple(self.exits.create(choice.name, choice.params) for choice in exit_choices),
            filters=tuple(self.filters.create(choice.name, choice.params) for choice in filters),
        )


default_catalog = RuleCatalog()
