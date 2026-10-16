"""Priority rules: which signals a portfolio takes first when more fire on one close than it has room for.

A rule scores every bar of a ticker once per run from the ticker's own closes; on a close, the signals with
the highest scores go first. Scores are causal and NaN while their lookback is warming up; a signal without
a score goes after every signal with one. Shorts mirror longs, so the weakest tickers go first for them.
New rules plug in with `@priority_rules.register`.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass

import numpy as np

from tradescan.backtest.rules import Bars, Rule, RuleRegistry
from tradescan.params import param
from tradescan.signals.base import Direction


class PriorityRule(Rule):
    @abstractmethod
    def strength(self, bars: Bars) -> np.ndarray:
        """Causal: how strong the ticker is at each close, higher is stronger; NaN while warming up."""

    def scores(self, bars: Bars, direction: Direction) -> np.ndarray:
        """Higher goes first: the strongest tickers for longs, the weakest for shorts."""
        return direction.sign * self.strength(bars)


priority_rules: RuleRegistry[PriorityRule] = RuleRegistry("priority")


def _shifted(close: np.ndarray, bars: int) -> np.ndarray:
    """The close `bars` bars earlier at each bar; NaN where there is none."""
    shifted = np.full(len(close), np.nan)
    if bars < len(close):
        shifted[bars:] = close[: len(close) - bars]
    return shifted


@priority_rules.register
@dataclass(frozen=True)
class RelativeStrengthPriority(PriorityRule):
    periods: tuple[int, ...] = param(
        (63, 126, 189, 252), minimum=1, maximum=1000, step=1, label="Lookbacks", unit="bars",
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
            raise ValueError(f"{self.name}: {len(self.periods)} lookbacks need as many weights, got {len(self.weights)}")
        if not any(self.weights):
            raise ValueError(f"{self.name}: at least one weight must be above 0")

    def strength(self, bars: Bars) -> np.ndarray:
        total = np.zeros(len(bars))
        for period, weight in zip(self.periods, self.weights):
            total += weight * (bars.close / _shifted(bars.close, period) - 1.0)
        return total


@priority_rules.register
@dataclass(frozen=True)
class MomentumPriority(PriorityRule):
    lookback: int = param(252, minimum=2, maximum=1000, step=1, label="Lookback", unit="bars")
    skip: int = param(
        21, minimum=0, maximum=250, step=1, label="Skip", unit="bars",
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


DEFAULT_PRIORITY = RelativeStrengthPriority.name
