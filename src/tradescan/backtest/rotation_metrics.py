"""Metrics of a rotation run: the metrics of a single-ticker backtest on the shared equity, and how the rotation
held and traded.

As for a portfolio, buy & hold is the benchmark's over the same dates and exposure is the share of closes with a
holding. A rotation's trades have no stop and so no R multiple, which leaves expectancy and SQN empty.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import pandas as pd

from tradescan.backtest.metrics import Metrics, compute_metrics
from tradescan.backtest.rotation import RotationResult


@dataclass(frozen=True)
class RotationStats:
    rebalances: int
    orders: int  # orders filled
    unfilled_orders: int  # dropped because their ticker had no bar before the next rebalance
    average_holdings: float  # tickers held, the safe asset included, averaged over the closes
    max_holdings: int
    average_exposure_pct: float  # gross value of the holdings, % of equity, averaged over the closes
    average_safe_pct: float  # value of the safe asset, % of equity, averaged over the closes
    average_cash_pct: float  # the rest
    turnover_pct: float  # half the value traded per year, % of the average equity
    commissions: float


@dataclass(frozen=True)
class RotationMetrics:
    metrics: Metrics
    stats: RotationStats


def rotation_metrics(result: RotationResult, benchmark_close: pd.Series, bars_per_year: int) -> RotationMetrics:
    """The benchmark's closes may be on other dates; each close of the run takes the benchmark's last close at or
    before it."""
    equity, holdings = result.equity, result.holdings
    benchmark = benchmark_close.astype(float).reindex(equity.index, method="ffill").dropna()
    metrics = compute_metrics(
        equity, [item.trade for item in result.trades], benchmark if len(benchmark) else equity, bars_per_year
    )
    metrics = replace(
        metrics,
        exposure_pct=float((holdings > 0).mean() * 100.0) if len(holdings) else math.nan,
        buy_hold_pct=metrics.buy_hold_pct if len(benchmark) else math.nan,
    )
    years = (len(equity) - 1) / bars_per_year
    average_equity = float(equity.mean())
    exposure = _average(result.exposure_pct)
    stats = RotationStats(
        rebalances=result.rebalances,
        orders=result.orders,
        unfilled_orders=result.unfilled,
        average_holdings=float(holdings.mean()) if len(holdings) else math.nan,
        max_holdings=int(holdings.max()) if len(holdings) else 0,
        average_exposure_pct=exposure,
        average_safe_pct=_average(result.safe_pct),
        average_cash_pct=100.0 - exposure,
        turnover_pct=result.traded_value / 2.0 / average_equity / years * 100.0
        if years > 0 and average_equity > 0
        else math.nan,
        commissions=result.commissions,
    )
    return RotationMetrics(metrics, stats)


def _average(series: pd.Series) -> float:
    return float(series.mean()) if series.notna().any() else math.nan
