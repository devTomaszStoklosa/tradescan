"""In-sample and out-of-sample periods: the same trade rules on the history used for tuning and on the rest.

The history is split once, at `split_index`. The out-of-sample period is the last `oos_pct` percent of
the bars, which no tuning should look at:

* the in-sample run only gets the bars before the split, so it cannot see later data;
* the out-of-sample run gets the full history, so indicators are warmed up, but its signal only fires
  from the split on; it starts with fresh equity and its metrics start at the split bar.

Both periods are run by the engine the caller passes in, so every engine reports them the same way.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from tradescan.backtest.base import BacktestConfig, BacktestEngine, BacktestResult
from tradescan.backtest.metrics import Metrics, compute_metrics
from tradescan.backtest.trade_rules import TradeRules
from tradescan.signals.base import Signal

MIN_PERIOD_BARS = 60  # fewer bars than this in either period leaves too little to judge


@dataclass(frozen=True)
class Split:
    oos_pct: float
    index: int  # the first out-of-sample bar
    in_sample: tuple[pd.Timestamp, pd.Timestamp]  # first and last bar
    out_of_sample: tuple[pd.Timestamp, pd.Timestamp]


@dataclass(frozen=True)
class PeriodMetrics:
    in_sample: Metrics
    out_of_sample: Metrics


def split_index(bars: int, oos_pct: float) -> int | None:
    """The first out-of-sample bar; None when either period would have fewer than MIN_PERIOD_BARS bars."""
    index = math.floor(bars * (1.0 - oos_pct / 100.0))
    if index < MIN_PERIOD_BARS or bars - index < MIN_PERIOD_BARS:
        return None
    return index


def split_history(dates: pd.DatetimeIndex, oos_pct: float) -> Split | None:
    index = split_index(len(dates), oos_pct)
    if index is None:
        return None
    return Split(
        oos_pct=oos_pct,
        index=index,
        in_sample=(dates[0], dates[index - 1]),
        out_of_sample=(dates[index], dates[-1]),
    )


class SignalFrom(Signal):
    """`signal` with its events before bar `start` removed. Its condition is unchanged, so indicators that
    need a long history are still warmed up when the events start."""

    def __init__(self, signal: Signal, start: int) -> None:
        self._signal = signal
        self._start = start
        self.name = signal.name  # type: ignore[misc]
        self.family = signal.family  # type: ignore[misc]
        self.direction = signal.direction  # type: ignore[misc]
        self.description = signal.description  # type: ignore[misc]

    def condition(self, df: pd.DataFrame) -> pd.Series:
        return self._signal.condition(df)

    def events(self, df: pd.DataFrame) -> pd.Series:
        events = self._signal.events(df).copy()
        events.iloc[: self._start] = False
        return events

    def describe(self) -> str:
        return self._signal.describe()


class SignalSince(SignalFrom):
    """`signal` with its events before the date `start` removed, for tickers whose bars start on different dates."""

    def __init__(self, signal: Signal, start: pd.Timestamp) -> None:
        super().__init__(signal, 0)
        self._since = start

    def events(self, df: pd.DataFrame) -> pd.Series:
        events = self._signal.events(df).copy()
        events[events.index < self._since] = False
        return events


@dataclass(frozen=True)
class PeriodResults:
    in_sample: BacktestResult  # on the bars before the split
    out_of_sample: BacktestResult  # on the full history, with trades from the split on only


def run_period_results(
    engine: BacktestEngine,
    ticker: str,
    df: pd.DataFrame,
    signal: Signal,
    config: BacktestConfig,
    rules: TradeRules,
    split: int,
) -> PeriodResults:
    """The in-sample and the out-of-sample run, split at bar `split` (see the module docstring)."""
    return PeriodResults(
        in_sample=engine.run(ticker, df.iloc[:split], signal, config, rules),
        out_of_sample=engine.run(ticker, df, SignalFrom(signal, split), config, rules),
    )


def period_metrics(results: PeriodResults, df: pd.DataFrame, split: int, bars_per_year: int) -> PeriodMetrics:
    """Metrics of both runs; the out-of-sample ones start at the split bar."""
    early, late = results.in_sample, results.out_of_sample
    return PeriodMetrics(
        in_sample=compute_metrics(early.equity, early.trades, df["close"].iloc[:split], bars_per_year),
        out_of_sample=compute_metrics(late.equity.iloc[split:], late.trades, df["close"].iloc[split:], bars_per_year),
    )


def run_periods(
    engine: BacktestEngine,
    ticker: str,
    df: pd.DataFrame,
    signal: Signal,
    config: BacktestConfig,
    rules: TradeRules,
    split: int,
) -> PeriodMetrics:
    """Metrics of the in-sample and the out-of-sample run, split at bar `split` (see the module docstring)."""
    results = run_period_results(engine, ticker, df, signal, config, rules, split)
    return period_metrics(results, df, split, config.bars_per_year)
