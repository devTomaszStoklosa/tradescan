"""Candlestick and gap patterns."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradescan.indicators import relative_volume, sma
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.registry import register


@dataclass(frozen=True)
class _GapAndGo(Signal):
    min_gap_pct: float = 2.0
    rvol_period: int = 20
    min_rvol: float = 1.5
    family = Family.PATTERN

    def condition(self, df: pd.DataFrame) -> pd.Series:
        gap = df["open"] / df["close"].shift(1) - 1.0
        heavy = relative_volume(df["volume"], self.rvol_period) >= self.min_rvol
        threshold = self.min_gap_pct / 100.0
        if self.direction is Direction.LONG:
            return (gap >= threshold) & (df["close"] > df["open"]) & heavy
        return (gap <= -threshold) & (df["close"] < df["open"]) & heavy


@register
class GapAndGoUp(_GapAndGo):
    name = "gap_and_go_up"
    direction = Direction.LONG
    description = "Gap up >= 2% that closes above the open on >= 1.5x volume"


@register
class GapAndGoDown(_GapAndGo):
    name = "gap_and_go_down"
    direction = Direction.SHORT
    description = "Gap down >= 2% that closes below the open on >= 1.5x volume"


@dataclass(frozen=True)
class _Engulfing(Signal):
    trend_period: int = 20
    family = Family.PATTERN

    def condition(self, df: pd.DataFrame) -> pd.Series:
        open_, close = df["open"], df["close"]
        previous_open, previous_close = open_.shift(1), close.shift(1)
        previous_trend = sma(close, self.trend_period).shift(1)
        if self.direction is Direction.LONG:
            return (
                (previous_close < previous_open)
                & (close > open_)
                & (open_ <= previous_close)
                & (close >= previous_open)
                & (previous_close < previous_trend)
            )
        return (
            (previous_close > previous_open)
            & (close < open_)
            & (open_ >= previous_close)
            & (close <= previous_open)
            & (previous_close > previous_trend)
        )


@register
class BullishEngulfing(_Engulfing):
    name = "bullish_engulfing"
    direction = Direction.LONG
    description = "Bullish candle engulfing a bearish one after a pullback below SMA(20)"


@register
class BearishEngulfing(_Engulfing):
    name = "bearish_engulfing"
    direction = Direction.SHORT
    description = "Bearish candle engulfing a bullish one after a rally above SMA(20)"
