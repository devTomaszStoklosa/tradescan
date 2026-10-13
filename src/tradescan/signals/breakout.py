"""Breakout and volatility-contraction signals."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradescan.indicators import bollinger, donchian, keltner, relative_volume
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.registry import register


@dataclass(frozen=True)
class _DonchianBreak(Signal):
    period: int = 20
    family = Family.BREAKOUT

    def condition(self, df: pd.DataFrame) -> pd.Series:
        channel = donchian(df, self.period).shift(1)  # the previous N bars, excluding today
        if self.direction is Direction.LONG:
            return df["close"] > channel["upper"]
        return df["close"] < channel["lower"]


@register
class DonchianBreakout(_DonchianBreak):
    name = "donchian_breakout"
    direction = Direction.LONG
    description = "Close above the highest high of the previous 20 bars (Turtle entry)"


@register
class DonchianBreakdown(_DonchianBreak):
    name = "donchian_breakdown"
    direction = Direction.SHORT
    description = "Close below the lowest low of the previous 20 bars"


@register
@dataclass(frozen=True)
class High52wBreakout(Signal):
    period: int = 252
    volume_period: int = 50
    min_rvol: float = 1.5
    name = "high_52w_breakout"
    family = Family.BREAKOUT
    direction = Direction.LONG
    description = "Close at a new 52-week high on volume >= 1.5x the 50-day average"

    def condition(self, df: pd.DataFrame) -> pd.Series:
        prior_high = df["high"].rolling(self.period, min_periods=self.period).max().shift(1)
        rvol = relative_volume(df["volume"], self.volume_period)
        return (df["close"] > prior_high) & (rvol >= self.min_rvol)


@dataclass(frozen=True)
class _SqueezeRelease(Signal):
    period: int = 20
    bb_mult: float = 2.0
    kc_mult: float = 1.5
    min_squeeze_bars: int = 5
    family = Family.BREAKOUT

    def condition(self, df: pd.DataFrame) -> pd.Series:
        bands = bollinger(df["close"], self.period, self.bb_mult)
        channel = keltner(df, self.period, self.kc_mult)
        squeeze = (bands["upper"] < channel["upper"]) & (bands["lower"] > channel["lower"])
        held = squeeze.shift(1, fill_value=False).astype(float).rolling(self.min_squeeze_bars).sum()
        released = (held >= self.min_squeeze_bars) & ~squeeze
        if self.direction is Direction.LONG:
            return released & (df["close"] > bands["mid"])
        return released & (df["close"] < bands["mid"])


@register
class SqueezeReleaseUp(_SqueezeRelease):
    name = "squeeze_release_up"
    direction = Direction.LONG
    description = "Bollinger Bands leave a 5+ bar Keltner squeeze with price above the midline (TTM squeeze)"


@register
class SqueezeReleaseDown(_SqueezeRelease):
    name = "squeeze_release_down"
    direction = Direction.SHORT
    description = "Bollinger Bands leave a 5+ bar Keltner squeeze with price below the midline"


@dataclass(frozen=True)
class _Nr7Break(Signal):
    lookback: int = 7
    family = Family.BREAKOUT

    def condition(self, df: pd.DataFrame) -> pd.Series:
        bar_range = df["high"] - df["low"]
        narrowest = bar_range <= bar_range.rolling(self.lookback, min_periods=self.lookback).min()
        after_nr7 = narrowest.shift(1, fill_value=False)
        if self.direction is Direction.LONG:
            return after_nr7 & (df["close"] > df["high"].shift(1))
        return after_nr7 & (df["close"] < df["low"].shift(1))


@register
class Nr7Breakout(_Nr7Break):
    name = "nr7_breakout"
    direction = Direction.LONG
    description = "Close above the high of an NR7 bar (narrowest range of 7)"


@register
class Nr7Breakdown(_Nr7Break):
    name = "nr7_breakdown"
    direction = Direction.SHORT
    description = "Close below the low of an NR7 bar"
