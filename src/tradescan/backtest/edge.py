"""Historical edge of a signal: what happened after its past occurrences."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from tradescan.signals.base import Signal


def forward_returns(df: pd.DataFrame, horizon: int) -> pd.Series:
    """Return from the next bar's open to the close `horizon` bars after the signal bar.

    This deliberately looks ahead: it is the outcome label for past events, never an input to a signal.
    """
    if horizon < 1:
        raise ValueError("horizon must be at least 1 bar")
    return df["close"].shift(-horizon) / df["open"].shift(-1) - 1.0


@dataclass(frozen=True)
class EdgeStats:
    signal: str
    horizon: int
    events: int
    win_rate: float
    mean_return: float
    median_return: float
    baseline_return: float

    @property
    def edge(self) -> float:
        """Mean return after the signal minus the mean return of entering on any bar."""
        return self.mean_return - self.baseline_return


class EdgeAnalyzer:
    def __init__(self, horizon: int) -> None:
        self._horizon = horizon

    @property
    def horizon(self) -> int:
        return self._horizon

    def analyze(self, frames: Sequence[pd.DataFrame], signal: Signal) -> EdgeStats:
        """Pool the events of `signal` across `frames` (one ticker, or a whole watchlist).

        Returns are in the signal's direction, so a profitable short counts as a positive return.
        """
        samples: list[pd.Series] = []
        baselines: list[pd.Series] = []
        for df in frames:
            outcome = forward_returns(df, self._horizon) * signal.direction.sign
            samples.append(outcome[signal.events(df)].dropna())
            baselines.append(outcome.dropna())

        sample = pd.concat(samples) if samples else pd.Series(dtype=float)
        baseline = pd.concat(baselines) if baselines else pd.Series(dtype=float)
        has_events = not sample.empty
        return EdgeStats(
            signal=signal.name,
            horizon=self._horizon,
            events=len(sample),
            win_rate=float((sample > 0).mean() * 100.0) if has_events else math.nan,
            mean_return=float(sample.mean() * 100.0) if has_events else math.nan,
            median_return=float(sample.median() * 100.0) if has_events else math.nan,
            baseline_return=float(baseline.mean() * 100.0) if not baseline.empty else math.nan,
        )
