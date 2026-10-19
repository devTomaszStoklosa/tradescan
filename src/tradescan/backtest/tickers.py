"""One backtest setup on many tickers: the job a task runner runs for each ticker.

Every ticker is split on its own bars by `oos.split_history`, as a single backtest of it would be, so a
ticker's result here is the result of backtesting that ticker alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd

from tradescan.backtest.base import BacktestConfig, BacktestResult
from tradescan.backtest.metrics import Metrics, compute_metrics
from tradescan.backtest.oos import Split, period_metrics, run_period_results, split_history
from tradescan.backtest.trade_rules import TradeRules
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.signals.base import Signal


class Period(StrEnum):
    FULL = "full"  # the whole history
    IN_SAMPLE = "in_sample"
    OUT_OF_SAMPLE = "out_of_sample"


@dataclass(frozen=True)
class PeriodRun:
    metrics: Metrics
    r_multiples: np.ndarray  # of the closed trades, so trades of many tickers can be pooled


@dataclass(frozen=True)
class TickerRun:
    full: PeriodRun
    split: Split | None  # None when the history is too short to split
    in_sample: PeriodRun | None
    out_of_sample: PeriodRun | None

    def period(self, period: Period) -> PeriodRun | None:
        return {Period.FULL: self.full, Period.IN_SAMPLE: self.in_sample, Period.OUT_OF_SAMPLE: self.out_of_sample}[
            period
        ]


def _r_multiples(result: BacktestResult) -> np.ndarray:
    return np.array([trade.r_multiple for trade in result.trades if trade.is_closed], dtype=float)


@dataclass(frozen=True)
class TickerJob:
    """Backtests one (ticker, bars) pair on the full history and on both periods. A module-level callable,
    so worker processes can unpickle it."""

    signal: Signal
    rules: TradeRules
    config: BacktestConfig

    def __call__(self, item: tuple[str, pd.DataFrame]) -> TickerRun:
        ticker, df = item
        engine = VectorizedEngine()
        result = engine.run(ticker, df, self.signal, self.config, self.rules)
        full = PeriodRun(
            compute_metrics(result.equity, result.trades, df["close"], self.config.bars_per_year), _r_multiples(result)
        )
        split = split_history(df.index, self.config.oos_pct)
        if split is None:
            return TickerRun(full, None, None, None)
        results = run_period_results(engine, ticker, df, self.signal, self.config, self.rules, split.index)
        metrics = period_metrics(results, df, split.index, self.config.bars_per_year)
        return TickerRun(
            full=full,
            split=split,
            in_sample=PeriodRun(metrics.in_sample, _r_multiples(results.in_sample)),
            out_of_sample=PeriodRun(metrics.out_of_sample, _r_multiples(results.out_of_sample)),
        )
