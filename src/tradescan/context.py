"""Per-ticker facts on the latest bar: price, volatility, daily/weekly trend and raw relative strength.

The trends and the relative strength are also available at every bar at once (`daily_trends`, `weekly_trends`,
`relative_strengths`), each bar seeing only the bars up to it, for a backtest that scores like the scanner.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd

from tradescan.indicators import adx, atr, rate_of_change, sma

# IBD-style relative strength: the latest quarter counts double.
_RS_PERIODS: tuple[int, ...] = (63, 126, 189, 252)
_RS_WEIGHTS: tuple[float, ...] = (0.4, 0.2, 0.2, 0.2)


class Trend(StrEnum):
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class TickerContext:
    ticker: str
    date: pd.Timestamp
    close: float
    change_pct: float
    atr: float
    atr_pct: float
    adx: float
    daily_trend: Trend
    weekly_trend: Trend
    rs_raw: float


class ContextBuilder:
    def __init__(
        self,
        atr_period: int = 14,
        fast_period: int = 50,
        slow_period: int = 200,
        weekly_period: int = 30,
        rs_periods: Sequence[int] = _RS_PERIODS,
        rs_weights: Sequence[float] = _RS_WEIGHTS,
    ) -> None:
        if len(rs_periods) != len(rs_weights):
            raise ValueError("relative strength needs one weight per lookback")
        self._atr_period = atr_period
        self._fast_period = fast_period
        self._slow_period = slow_period
        self._weekly_period = weekly_period
        self._rs_weights = tuple(zip(rs_periods, rs_weights))

    def build(self, ticker: str, df: pd.DataFrame) -> TickerContext:
        close = df["close"]
        last_close = float(close.iloc[-1])
        last_atr = float(atr(df, self._atr_period).iloc[-1])
        return TickerContext(
            ticker=ticker,
            date=df.index[-1],
            close=last_close,
            change_pct=float(close.pct_change().iloc[-1] * 100.0) if len(close) > 1 else math.nan,
            atr=last_atr,
            atr_pct=last_atr / last_close * 100.0 if last_close else math.nan,
            adx=float(adx(df, self._atr_period)["adx"].iloc[-1]),
            daily_trend=self._daily_trend(close),
            weekly_trend=self._weekly_trend(close),
            rs_raw=self._relative_strength(close),
        )

    def _daily_trend(self, close: pd.Series) -> Trend:
        last = close.iloc[-1]
        fast = sma(close, self._fast_period).iloc[-1]
        slow = sma(close, self._slow_period).iloc[-1]
        if pd.isna(fast) or pd.isna(slow):
            return Trend.NEUTRAL
        if last > slow and fast > slow:
            return Trend.UP
        if last < slow and fast < slow:
            return Trend.DOWN
        return Trend.NEUTRAL

    def _weekly_trend(self, close: pd.Series) -> Trend:
        """Weinstein-style stage: weekly close vs a rising/falling 30-week SMA. The current week may be partial."""
        weekly = close.resample("W-FRI").last().dropna()
        average = sma(weekly, self._weekly_period)
        if len(average.dropna()) < 2:
            return Trend.NEUTRAL
        last, current, previous = weekly.iloc[-1], average.iloc[-1], average.iloc[-2]
        if last > current and current > previous:
            return Trend.UP
        if last < current and current < previous:
            return Trend.DOWN
        return Trend.NEUTRAL

    def _relative_strength(self, close: pd.Series) -> float:
        total = 0.0
        for period, weight in self._rs_weights:
            change = rate_of_change(close, period).iloc[-1] if len(close) > period else math.nan
            if pd.isna(change):
                return math.nan
            total += weight * float(change)
        return total

    # --- At every bar: what `build` would report on the history up to that bar ------------------------

    def daily_trends(self, close: pd.Series) -> np.ndarray:
        """The daily trend at each bar as 1 (up), -1 (down) or 0 (neutral, also while the SMAs warm up)."""
        last = close.to_numpy(dtype=float)
        fast = sma(close, self._fast_period).to_numpy(dtype=float)
        slow = sma(close, self._slow_period).to_numpy(dtype=float)
        up = (last > slow) & (fast > slow)
        down = (last < slow) & (fast < slow)
        return up.astype(int) - down.astype(int)

    def weekly_trends(self, close: pd.Series) -> np.ndarray:
        """The weekly trend at each bar as 1 (up), -1 (down) or 0, with the bar's own week partial: it closes at
        the bar, as the latest week does in `build`."""
        values = close.to_numpy(dtype=float)
        period = self._weekly_period
        trends = np.zeros(len(values), dtype=int)
        if not len(values):
            return trends
        weeks = close.index.to_period("W-FRI").asi8  # the bins of resample("W-FRI")
        starts = np.r_[True, weeks[1:] != weeks[:-1]]
        week = np.cumsum(starts) - 1  # each bar's week among the weeks with a bar
        weekly = pd.Series(values[np.r_[np.flatnonzero(starts)[1:] - 1, len(values) - 1]])  # each week's last close
        previous = sma(weekly, period).to_numpy(dtype=float)
        others = weekly.rolling(period - 1).sum().to_numpy(dtype=float) if period > 1 else np.zeros(len(weekly))

        ready = week >= period  # the partial week's average and the one before it both exist
        k, last = week[ready], values[ready]
        before = previous[k - 1]  # the average up to the week before
        current = (others[k - 1] + last) / period  # with the partial week closing at the bar
        up = (last > current) & (current > before)
        down = (last < current) & (current < before)
        trends[ready] = up.astype(int) - down.astype(int)
        return trends

    def relative_strengths(self, close: pd.Series) -> np.ndarray:
        """The raw relative strength at each bar; NaN until every lookback has a bar to compare with."""
        total = np.zeros(len(close))
        for period, weight in self._rs_weights:
            total += weight * rate_of_change(close, period).to_numpy(dtype=float)
        return total
