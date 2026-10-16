"""Performance metrics computed identically for every engine."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from tradescan.backtest.base import Trade


@dataclass(frozen=True)
class Metrics:
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    sortino: float
    max_drawdown_pct: float
    trades: int
    win_rate_pct: float
    profit_factor: float
    expectancy_r: float
    sqn: float
    exposure_pct: float
    buy_hold_pct: float


def compute_metrics(
    equity: pd.Series,
    trades: Sequence[Trade],
    close: pd.Series,
    bars_per_year: int = 252,
) -> Metrics:
    returns = equity.pct_change().dropna()
    closed = [trade for trade in trades if trade.is_closed]
    r_multiples = np.array([trade.r_multiple for trade in closed], dtype=float)
    pnls = np.array([trade.pnl for trade in closed], dtype=float)
    gross_win = pnls[pnls > 0].sum()
    gross_loss = -pnls[pnls < 0].sum()

    return Metrics(
        total_return_pct=(equity.iloc[-1] / equity.iloc[0] - 1.0) * 100.0,
        cagr_pct=_cagr(equity, bars_per_year) * 100.0,
        sharpe=_ratio(returns.mean(), returns.std(ddof=1), bars_per_year),
        sortino=_ratio(returns.mean(), math.sqrt((returns.clip(upper=0.0) ** 2).mean()), bars_per_year),
        max_drawdown_pct=float((equity / equity.cummax() - 1.0).min() * 100.0),
        trades=len(closed),
        win_rate_pct=float((pnls > 0).mean() * 100.0) if len(pnls) else math.nan,
        profit_factor=float(gross_win / gross_loss) if gross_loss > 0 else (math.inf if gross_win > 0 else math.nan),
        expectancy_r=float(r_multiples.mean()) if len(r_multiples) else math.nan,
        sqn=sqn(r_multiples),
        exposure_pct=_exposure(trades, equity.index) * 100.0,
        buy_hold_pct=(close.iloc[-1] / close.iloc[0] - 1.0) * 100.0,
    )


def _cagr(equity: pd.Series, bars_per_year: int) -> float:
    years = (len(equity) - 1) / bars_per_year
    if years <= 0 or equity.iloc[0] <= 0 or equity.iloc[-1] <= 0:
        return math.nan
    return (equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0


def _ratio(mean: float, deviation: float, bars_per_year: int) -> float:
    if not deviation or math.isnan(deviation):
        return math.nan
    return float(mean / deviation * math.sqrt(bars_per_year))


def sqn(r_multiples: np.ndarray) -> float:
    """Van Tharp's System Quality Number: sqrt(N) * mean(R) / std(R)."""
    if len(r_multiples) < 2 or r_multiples.std(ddof=1) == 0:
        return math.nan
    return float(math.sqrt(len(r_multiples)) * r_multiples.mean() / r_multiples.std(ddof=1))


def _exposure(trades: Sequence[Trade], index: pd.DatetimeIndex) -> float:
    """Share of bars with an open position (entry bar through the bar before the exit fill)."""
    if len(index) == 0:
        return math.nan
    held = 0
    for trade in trades:
        start = index.get_loc(trade.entry_date)
        end = index.get_loc(trade.exit_date)
        held += max(end - start, 1) if trade.is_closed else end - start + 1
    return held / len(index)
