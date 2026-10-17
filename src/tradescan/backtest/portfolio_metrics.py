"""Metrics of a portfolio run: the metrics of a single-ticker backtest on the shared equity, how full the
portfolio was, and what each ticker contributed.

Two metrics change meaning: buy & hold is the benchmark's over the same dates, and exposure is the share of
closes with at least one open position (the gross exposure is in the stats).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol

import numpy as np
import pandas as pd

from tradescan.backtest.base import Trade
from tradescan.backtest.metrics import Metrics, compute_metrics
from tradescan.backtest.portfolio import PortfolioResult, PortfolioTrade


@dataclass(frozen=True)
class PortfolioStats:
    average_positions: float  # open positions, averaged over the closes
    max_positions: int
    average_exposure_pct: float  # gross value of the open positions, % of equity, averaged over the closes
    max_exposure_pct: float
    orders: int  # entry orders placed
    skipped_no_slot: int  # signals skipped because every slot was taken
    skipped_no_room: int  # signals skipped because less than one lot fitted under the exposure cap


@dataclass(frozen=True)
class PortfolioMetrics:
    metrics: Metrics
    stats: PortfolioStats


def portfolio_metrics(
    result: PortfolioResult, benchmark_close: pd.Series, bars_per_year: int, start: pd.Timestamp | None = None
) -> PortfolioMetrics:
    """Metrics from the close of `start` on, with the trades entered from then on, or of the whole run. The
    benchmark's closes may be on other dates; each close of the run takes the benchmark's last close at or before it."""
    equity = result.equity.loc[start:] if start is not None else result.equity
    positions = result.positions.loc[equity.index]
    exposure = result.exposure_pct.loc[equity.index]
    benchmark = benchmark_close.astype(float).reindex(equity.index, method="ffill").dropna()
    trades = [item.trade for item in result.trades if start is None or item.trade.entry_date >= start]
    metrics = compute_metrics(equity, trades, benchmark if len(benchmark) else equity, bars_per_year)
    metrics = replace(
        metrics,
        exposure_pct=float((positions > 0).mean() * 100.0) if len(positions) else math.nan,
        buy_hold_pct=metrics.buy_hold_pct if len(benchmark) else math.nan,
    )
    stats = PortfolioStats(
        average_positions=float(positions.mean()) if len(positions) else math.nan,
        max_positions=int(positions.max()) if len(positions) else 0,
        average_exposure_pct=float(exposure.mean()) if exposure.notna().any() else math.nan,
        max_exposure_pct=float(exposure.max()) if exposure.notna().any() else math.nan,
        orders=result.orders,
        skipped_no_slot=result.no_slot,
        skipped_no_room=result.no_room,
    )
    return PortfolioMetrics(metrics, stats)


@dataclass(frozen=True)
class TickerContribution:
    ticker: str
    trades: int  # closed trades
    pnl: float  # net, with a trade still open marked to its last close
    contribution_pct: float  # pnl as a percent of the initial equity
    win_rate_pct: float  # of the closed trades
    expectancy_r: float  # of the closed trades


class TickerTrades(Protocol):
    """A run whose trades carry their ticker: a portfolio's or a rotation's."""

    @property
    def tickers(self) -> tuple[str, ...]: ...

    @property
    def trades(self) -> Sequence[PortfolioTrade]: ...


def contributions(result: TickerTrades, initial_equity: float) -> list[TickerContribution]:
    """Every ticker of the run in watchlist order, also those that never traded."""
    by_ticker: dict[str, list[Trade]] = {ticker: [] for ticker in result.tickers}
    for item in result.trades:
        by_ticker[item.ticker].append(item.trade)
    rows = []
    for ticker, trades in by_ticker.items():
        closed = [trade for trade in trades if trade.is_closed]
        pnls = np.array([trade.pnl for trade in closed], dtype=float)
        r_multiples = np.array([trade.r_multiple for trade in closed], dtype=float)
        pnl = float(sum(trade.pnl for trade in trades))
        rows.append(
            TickerContribution(
                ticker=ticker,
                trades=len(closed),
                pnl=pnl,
                contribution_pct=pnl / initial_equity * 100.0 if initial_equity else math.nan,
                win_rate_pct=float((pnls > 0).mean() * 100.0) if len(pnls) else math.nan,
                expectancy_r=float(r_multiples.mean()) if len(r_multiples) else math.nan,
            )
        )
    return rows
