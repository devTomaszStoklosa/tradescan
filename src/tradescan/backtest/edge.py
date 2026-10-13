"""Historical edge of a signal: what happened after its past occurrences."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np
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


@dataclass(frozen=True)
class EdgeSample:
    """Outcomes of one signal on one ticker at one horizon, in the signal's direction.

    Samples from many tickers combine into one `EdgeStats` without keeping the price frames.
    """

    returns: np.ndarray
    baseline_sum: float
    baseline_count: int


def edge_samples(
    df: pd.DataFrame,
    signal: Signal,
    horizons: Sequence[int],
    events: pd.Series | None = None,
) -> tuple[EdgeSample, ...]:
    """Samples for every horizon; the signal's events are computed once (or passed in if already known)."""
    flags = (signal.events(df) if events is None else events).to_numpy(dtype=bool)
    samples = []
    for horizon in horizons:
        outcome = (forward_returns(df, horizon) * signal.direction.sign).to_numpy()
        valid = ~np.isnan(outcome)
        samples.append(
            EdgeSample(
                returns=outcome[flags & valid],
                baseline_sum=float(outcome[valid].sum()),
                baseline_count=int(valid.sum()),
            )
        )
    return tuple(samples)


def combine_samples(signal: str, horizon: int, samples: Iterable[EdgeSample]) -> EdgeStats:
    """Pool samples from one or many tickers into win rate, mean, median and the all-bars baseline."""
    parts = list(samples)
    returns = np.concatenate([part.returns for part in parts]) if parts else np.array([])
    baseline_count = sum(part.baseline_count for part in parts)
    has_events = returns.size > 0
    return EdgeStats(
        signal=signal,
        horizon=horizon,
        events=int(returns.size),
        win_rate=float((returns > 0).mean() * 100.0) if has_events else math.nan,
        mean_return=float(returns.mean() * 100.0) if has_events else math.nan,
        median_return=float(np.median(returns) * 100.0) if has_events else math.nan,
        baseline_return=sum(part.baseline_sum for part in parts) / baseline_count * 100.0 if baseline_count else math.nan,
    )


@dataclass(frozen=True)
class EdgeSampler:
    """Per-ticker job for task runners: samples indexed [signal][horizon]. Module-level, so picklable."""

    signals: tuple[Signal, ...]
    horizons: tuple[int, ...]

    def __call__(self, df: pd.DataFrame) -> tuple[tuple[EdgeSample, ...], ...]:
        return tuple(edge_samples(df, signal, self.horizons) for signal in self.signals)
