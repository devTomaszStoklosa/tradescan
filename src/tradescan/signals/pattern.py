"""Candlestick and gap patterns."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradescan.indicators import relative_volume, sma
from tradescan.params import param
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.registry import register


@dataclass(frozen=True)
class _GapAndGo(Signal):
    min_gap_pct: float = param(2.0, minimum=0.1, maximum=20.0, step=0.1, label="Minimum gap", unit="%")
    rvol_period: int = param(20, minimum=5, maximum=200, step=1, label="Volume average", unit="bars")
    min_rvol: float = param(1.5, minimum=0.0, maximum=10.0, step=0.1, label="Minimum relative volume", unit="x")
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
    description = (
        "Gap up >= {min_gap_pct:g}% that closes above the open on >= {min_rvol:g}x the {rvol_period}-bar average volume"
    )


@register
class GapAndGoDown(_GapAndGo):
    name = "gap_and_go_down"
    direction = Direction.SHORT
    description = (
        "Gap down >= {min_gap_pct:g}% that closes below the open on >= {min_rvol:g}x the {rvol_period}-bar average volume"
    )


@dataclass(frozen=True)
class _Engulfing(Signal):
    trend_period: int = param(20, minimum=5, maximum=200, step=1, label="Trend SMA", unit="bars")
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
    description = "Bullish candle engulfing a bearish one after a pullback below SMA({trend_period})"


@register
class BearishEngulfing(_Engulfing):
    name = "bearish_engulfing"
    direction = Direction.SHORT
    description = "Bearish candle engulfing a bullish one after a rally above SMA({trend_period})"
