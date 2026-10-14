"""Breakout and volatility-contraction signals."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradescan.indicators import bollinger, donchian, keltner, relative_volume
from tradescan.params import param
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.registry import register


@dataclass(frozen=True)
class _DonchianBreak(Signal):
    period: int = param(20, minimum=2, maximum=300, step=1, label="Channel length", unit="bars")
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
    description = "Close above the highest high of the previous {period} bars (Turtle entry)"


@register
class DonchianBreakdown(_DonchianBreak):
    name = "donchian_breakdown"
    direction = Direction.SHORT
    description = "Close below the lowest low of the previous {period} bars"


@register
@dataclass(frozen=True)
class High52wBreakout(Signal):
    period: int = param(252, minimum=20, maximum=1000, step=1, label="High lookback", unit="bars")
    volume_period: int = param(50, minimum=5, maximum=200, step=1, label="Volume average", unit="bars")
    min_rvol: float = param(1.5, minimum=0.0, maximum=10.0, step=0.1, label="Minimum relative volume", unit="x")
    name = "high_52w_breakout"
    family = Family.BREAKOUT
    direction = Direction.LONG
    description = "Close at a new {period}-bar high on volume >= {min_rvol:g}x the {volume_period}-day average"

    def condition(self, df: pd.DataFrame) -> pd.Series:
        prior_high = df["high"].rolling(self.period, min_periods=self.period).max().shift(1)
        rvol = relative_volume(df["volume"], self.volume_period)
        return (df["close"] > prior_high) & (rvol >= self.min_rvol)


@dataclass(frozen=True)
class _SqueezeRelease(Signal):
    period: int = param(20, minimum=5, maximum=100, step=1, label="Band length", unit="bars")
    bb_mult: float = param(2.0, minimum=0.5, maximum=5.0, step=0.1, label="Bollinger width", unit="std")
    kc_mult: float = param(1.5, minimum=0.5, maximum=5.0, step=0.1, label="Keltner width", unit="ATR")
    min_squeeze_bars: int = param(5, minimum=1, maximum=50, step=1, label="Minimum squeeze", unit="bars")
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
    description = (
        "Bollinger Bands({period}, {bb_mult:g}) leave a {min_squeeze_bars}+ bar Keltner({kc_mult:g} ATR) squeeze "
        "with price above the midline (TTM squeeze)"
    )


@register
class SqueezeReleaseDown(_SqueezeRelease):
    name = "squeeze_release_down"
    direction = Direction.SHORT
    description = (
        "Bollinger Bands({period}, {bb_mult:g}) leave a {min_squeeze_bars}+ bar Keltner({kc_mult:g} ATR) squeeze "
        "with price below the midline"
    )


@dataclass(frozen=True)
class _Nr7Break(Signal):
    lookback: int = param(7, minimum=2, maximum=50, step=1, label="Narrowest-range lookback", unit="bars")
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
    description = "Close above the high of an NR{lookback} bar (narrowest range of {lookback})"


@register
class Nr7Breakdown(_Nr7Break):
    name = "nr7_breakdown"
    direction = Direction.SHORT
    description = "Close below the low of an NR{lookback} bar"
