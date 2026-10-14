"""Per-ticker facts on the latest bar: price, volatility, daily/weekly trend and raw relative strength."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

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
