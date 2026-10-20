"""Statistics over many tickers: their trades pooled in R, and the spread of one metric across them.

Trades are pooled by their R multiple, not their profit: each ticker's equity compounds on its own,
so a trade's profit depends on how the ticker did before it, while its R does not.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from tradescan.backtest.metrics import sqn

# Values above these are good, below them bad; the other metrics have no break-even.
BREAK_EVEN: dict[str, float] = {
    "total_return_pct": 0.0,
    "cagr_pct": 0.0,
    "sharpe": 0.0,
    "sortino": 0.0,
    "expectancy_r": 0.0,
    "sqn": 0.0,
    "profit_factor": 1.0,
}


@dataclass(frozen=True)
class PooledTrades:
    trades: int
    win_rate_pct: float
    expectancy_r: float
    profit_factor_r: float  # gross R won / gross R lost; infinite without losers
    sqn: float


def pool_trades(r_multiples: Iterable[np.ndarray]) -> PooledTrades:
    """Trade statistics of the closed trades of many tickers taken together."""
    parts = list(r_multiples)
    r = np.concatenate(parts) if parts else np.array([], dtype=float)
    won = float(r[r > 0].sum())
    lost = float(-r[r < 0].sum())
    return PooledTrades(
        trades=int(r.size),
        win_rate_pct=float((r > 0).mean() * 100.0) if r.size else math.nan,
        expectancy_r=float(r.mean()) if r.size else math.nan,
        profit_factor_r=won / lost if lost > 0 else (math.inf if won > 0 else math.nan),
        sqn=sqn(r),
    )


@dataclass(frozen=True)
class Spread:
    """How one metric is spread across tickers. Tickers without a value (NaN, e.g. no trades) are left out."""

    tickers: int  # tickers with a value
    median: float
    p25: float
    p75: float
    minimum: float
    maximum: float
    above_break_even_pct: float  # share of those tickers above break-even; NaN for metrics without one


def spread(values: Iterable[float], break_even: float | None = None) -> Spread:
    """The spread of `values`; an infinite value (a profit factor without losers) counts as the largest."""
    ordered = sorted(float(value) for value in values if not math.isnan(value))
    if not ordered:
        return Spread(0, math.nan, math.nan, math.nan, math.nan, math.nan, math.nan)
    above = sum(value > break_even for value in ordered) / len(ordered) * 100.0 if break_even is not None else math.nan
    return Spread(
        tickers=len(ordered),
        median=_quantile(ordered, 0.5),
        p25=_quantile(ordered, 0.25),
        p75=_quantile(ordered, 0.75),
        minimum=ordered[0],
        maximum=ordered[-1],
        above_break_even_pct=above,
    )


def _quantile(ordered: list[float], q: float) -> float:
    """Linear interpolation between the closest ranks, like numpy's default, but an infinite neighbour stays
    infinite instead of turning into NaN."""
    position = q * (len(ordered) - 1)
    low, high = math.floor(position), math.ceil(position)
    below, above = ordered[low], ordered[high]
    if low == high or below == above:
        return below
    return below + (above - below) * (position - low)
