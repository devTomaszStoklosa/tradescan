"""Priority rules: which signals a portfolio takes first when more fire on one close than it has room for.

A rule scores every bar of every ticker once per run, seeing the whole watchlist at once (`PriorityInputs`); on a
close, the signals with the highest scores go first. Scores are causal and NaN where there is none, e.g. while a
lookback is warming up; a signal without a score goes after every signal with one.

Most rules score each ticker from its own closes (`TickerPriorityRule`), and shorts mirror longs, so the weakest
tickers go first for them. The `score` rule is the scanner's confluence score, which ranks relative strength
within the watchlist and already scores the short side. It reads the scanner's settings and every signal, which
the portfolio use case adds with `with_scan`. New rules plug in with `@priority_rules.register`.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import ClassVar

import numpy as np
import pandas as pd

from tradescan.backtest.rules import Bars, Rule, RuleRegistry
from tradescan.context import ContextBuilder
from tradescan.params import param
from tradescan.scoring import Scorer
from tradescan.signals.base import Direction, Signal


@dataclass(frozen=True, eq=False)
class PriorityInputs:
    """What a priority rule reads: every ticker of the portfolio in watchlist order, on the shared calendar."""

    tickers: tuple[str, ...]
    bars: tuple[Bars, ...]
    days: tuple[np.ndarray, ...]  # the position of each ticker's bars in the shared calendar
    calendar: pd.DatetimeIndex
    direction: Direction


@dataclass(frozen=True, eq=False)
class ScanScore:
    """What the `score` rule reads besides the bars: the scanner's scorer and context builder, and each ticker's
    signal points on its own dates, the weights of the signals of `direction` that fired within the fresh window."""

    direction: Direction
    scorer: Scorer
    context: ContextBuilder
    signal_points: Mapping[str, pd.Series]

    @classmethod
    def build(
        cls,
        frames: Mapping[str, pd.DataFrame],
        signals: Sequence[Signal],
        direction: Direction,
        scorer: Scorer,
        context: ContextBuilder,
        fresh_bars: int,
    ) -> ScanScore:
        """Once per run, from every ticker's full history. Signals are causal, so a run on the bars before a date
        reads the same points as a run on every bar."""
        chosen = [signal for signal in signals if signal.direction is direction]
        points = {ticker: _signal_points(df, chosen, scorer, fresh_bars) for ticker, df in frames.items()}
        return cls(direction, scorer, context, points)

    def points(self, ticker: str, dates: pd.DatetimeIndex) -> np.ndarray:
        values = self.signal_points.get(ticker, pd.Series(dtype=float)).reindex(dates).to_numpy(dtype=float)
        if np.isnan(values).any():
            raise ValueError(
                f"The scan score has no signal points for every bar of {ticker}; build it from the full history"
            )
        return values


def _signal_points(df: pd.DataFrame, signals: Sequence[Signal], scorer: Scorer, fresh_bars: int) -> pd.Series:
    """At each bar, the weights of the signals that fired on it or on one of the `fresh_bars` - 1 bars before."""
    total = np.zeros(len(df))
    bars = np.arange(len(df))
    first = np.maximum(bars + 1 - fresh_bars, 0)
    for signal in signals:
        fired = np.r_[0, np.cumsum(signal.events(df).to_numpy(dtype=bool))]
        total += scorer.weight(signal) * (fired[bars + 1] > fired[first])
    return pd.Series(total, index=df.index)


def _percentiles(values: Sequence[np.ndarray], days: Sequence[np.ndarray], calendar_length: int) -> list[np.ndarray]:
    """Each ticker's percentile rank (0-100) at each bar among the tickers with a value on that calendar day."""
    table = np.full((calendar_length, len(values)), np.nan)
    for column, (value, day) in enumerate(zip(values, days, strict=True)):
        table[day, column] = value
    ranks = pd.DataFrame(table).rank(axis=1, pct=True).to_numpy() * 100.0
    return [ranks[day, column] for column, day in enumerate(days)]


class PriorityRule(Rule):
    needs_scan: ClassVar[bool] = False  # True when `scores` reads the scanner's score, which `with_scan` adds

    @abstractmethod
    def scores(self, inputs: PriorityInputs) -> list[np.ndarray]:
        """Per ticker in watchlist order, one causal score per bar: higher goes first, NaN for none."""

    def with_scan(self, scan: ScanScore) -> PriorityRule:
        """The rule with the scanner's score; a rule that does not read it ignores it."""
        return self


class TickerPriorityRule(PriorityRule):
    """A rule that scores each ticker from its own bars."""

    @abstractmethod
    def strength(self, bars: Bars) -> np.ndarray:
        """Causal: how strong the ticker is at each close, higher is stronger; NaN while warming up."""

    def scores(self, inputs: PriorityInputs) -> list[np.ndarray]:
        """The strongest tickers go first for longs, the weakest for shorts."""
        return [inputs.direction.sign * self.strength(bars) for bars in inputs.bars]


priority_rules: RuleRegistry[PriorityRule] = RuleRegistry("priority")


def _shifted(close: np.ndarray, bars: int) -> np.ndarray:
    """The close `bars` bars earlier at each bar; NaN where there is none."""
    shifted = np.full(len(close), np.nan)
    if bars < len(close):
        shifted[bars:] = close[: len(close) - bars]
    return shifted


@priority_rules.register
@dataclass(frozen=True)
class RelativeStrengthPriority(TickerPriorityRule):
    periods: tuple[int, ...] = param(
        (63, 126, 189, 252),
        minimum=1,
        maximum=1000,
        step=1,
        label="Lookbacks",
        unit="bars",
        help="Returns over these lookbacks are weighted into one score",
    )
    weights: tuple[float, ...] = param(
        (0.4, 0.2, 0.2, 0.2), minimum=0.0, maximum=10.0, step=0.05, label="Weights", help="One weight per lookback"
    )
    name = "relative_strength"
    label = "Relative strength"
    description = "Weighted returns over several lookbacks (IBD style by default: the latest quarter counts double)"

    def __post_init__(self) -> None:
        if len(self.periods) != len(self.weights):
            raise ValueError(
                f"{self.name}: {len(self.periods)} lookbacks need as many weights, got {len(self.weights)}"
            )
        if not any(self.weights):
            raise ValueError(f"{self.name}: at least one weight must be above 0")

    def strength(self, bars: Bars) -> np.ndarray:
        total = np.zeros(len(bars))
        for period, weight in zip(self.periods, self.weights, strict=True):
            total += weight * (bars.close / _shifted(bars.close, period) - 1.0)
        return total


@priority_rules.register
@dataclass(frozen=True)
class MomentumPriority(TickerPriorityRule):
    lookback: int = param(252, minimum=2, maximum=1000, step=1, label="Lookback", unit="bars")
    skip: int = param(
        21,
        minimum=0,
        maximum=250,
        step=1,
        label="Skip",
        unit="bars",
        help="The latest bars left out; 252 and 21 give the 12-1 month momentum",
    )
    name = "momentum"
    label = "Momentum"
    description = "Return from {lookback} bars ago to {skip} bars ago"

    def __post_init__(self) -> None:
        if self.skip >= self.lookback:
            raise ValueError(f"{self.name}: skip ({self.skip}) must be below the lookback ({self.lookback})")

    def strength(self, bars: Bars) -> np.ndarray:
        return _shifted(bars.close, self.skip) / _shifted(bars.close, self.lookback) - 1.0


@priority_rules.register
@dataclass(frozen=True)
class ScorePriority(PriorityRule):
    """The scanner's score at every close: the weights of the fresh signals of the portfolio's direction, the
    daily and weekly trend bonuses and the relative-strength bonus, with relative strength ranked among the
    tickers that have a bar that day."""

    scan: ScanScore | None = field(default=None, compare=False, repr=False)
    name = "score"
    label = "Scan score"
    description = "The scanner's confluence score: fresh signals, daily and weekly trend, relative-strength rank"
    needs_scan = True

    def with_scan(self, scan: ScanScore) -> ScorePriority:
        return replace(self, scan=scan)

    def scores(self, inputs: PriorityInputs) -> list[np.ndarray]:
        scan = self.scan
        if scan is None:
            raise ValueError(f"The {self.name} priority needs the scanner's settings and signals (with_scan)")
        if scan.direction is not inputs.direction:
            raise ValueError(
                f"The scan score holds {scan.direction.value} signals, the portfolio trades {inputs.direction.value}"
            )
        closes = [pd.Series(bars.close, index=bars.dates) for bars in inputs.bars]
        strengths = [scan.context.relative_strengths(close) for close in closes]
        percentiles = _percentiles(strengths, inputs.days, len(inputs.calendar))
        return [
            scan.scorer.bar_scores(
                inputs.direction,
                scan.points(ticker, bars.dates),
                scan.context.daily_trends(close),
                scan.context.weekly_trends(close),
                percentile,
            )
            for ticker, bars, close, percentile in zip(inputs.tickers, inputs.bars, closes, percentiles, strict=True)
        ]


DEFAULT_PRIORITY = RelativeStrengthPriority.name
