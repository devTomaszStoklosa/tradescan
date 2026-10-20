"""Map a watchlist backtest report."""

from __future__ import annotations

import math

from tradescan.api.mappers.backtest import metrics_out, rules_out, split_out
from tradescan.api.mappers.common import day, finite
from tradescan.api.schemas.backtest import MetricsOut
from tradescan.api.schemas.watchlist_backtest import (
    MetricSpreadOut,
    PeriodSummaryOut,
    PooledTradesOut,
    TickerRunOut,
    WatchlistBacktestOut,
)
from tradescan.backtest.pooled import PooledTrades, Spread
from tradescan.backtest.tickers import PeriodRun
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.services.watchlist_backtest import WatchlistBacktestReport


def pooled_trades_out(pooled: PooledTrades) -> PooledTradesOut:
    return PooledTradesOut(
        trades=pooled.trades,
        win_rate_pct=finite(pooled.win_rate_pct),
        expectancy_r=finite(pooled.expectancy_r),
        profit_factor_r=finite(pooled.profit_factor_r),
        profit_factor_infinite=math.isinf(pooled.profit_factor_r),
        sqn=finite(pooled.sqn),
    )


def spread_out(metric: str, spread: Spread) -> MetricSpreadOut:
    return MetricSpreadOut(
        metric=metric,
        tickers=spread.tickers,
        median=finite(spread.median),
        p25=finite(spread.p25),
        p75=finite(spread.p75),
        minimum=finite(spread.minimum),
        maximum=finite(spread.maximum),
        above_break_even_pct=finite(spread.above_break_even_pct),
    )


def watchlist_backtest_out(report: WatchlistBacktestReport) -> WatchlistBacktestOut:
    base = report.base

    def metrics(run: PeriodRun | None) -> MetricsOut | None:
        return metrics_out(run.metrics) if run else None

    return WatchlistBacktestOut(
        **rules_out(base.signal, base.config, base.rules, base.benchmark),
        universe=report.universe.name,
        engine=VectorizedEngine.name,
        rows=[
            TickerRunOut(
                ticker=row.ticker,
                start=day(row.start),
                end=day(row.end),
                split=split_out(row.run.split) if row.run.split else None,
                metrics=metrics_out(row.run.full.metrics),
                in_sample=metrics(row.run.in_sample),
                out_of_sample=metrics(row.run.out_of_sample),
            )
            for row in report.rows
        ],
        periods=[
            PeriodSummaryOut(
                period=period,
                tickers=summary.tickers,
                pooled=pooled_trades_out(summary.pooled),
                spread=[spread_out(metric, value) for metric, value in summary.spreads.items()],
            )
            for period, summary in report.periods.items()
        ],
        missing=report.missing,
    )
