"""Trend-following signals."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass

import pandas as pd

from tradescan.indicators import adx, ema, sma, supertrend
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.conditions import crossed_above, crossed_below
from tradescan.signals.registry import register


@dataclass(frozen=True)
class _MovingAverageCross(Signal):
    fast: int
    slow: int
    family = Family.TREND

    @abstractmethod
    def _average(self, close: pd.Series, period: int) -> pd.Series: ...

    def condition(self, df: pd.DataFrame) -> pd.Series:
        fast = self._average(df["close"], self.fast)
        slow = self._average(df["close"], self.slow)
        cross = crossed_above if self.direction is Direction.LONG else crossed_below
        return cross(fast, slow)


@dataclass(frozen=True)
class _SmaCross(_MovingAverageCross):
    fast: int = 50
    slow: int = 200

    def _average(self, close: pd.Series, period: int) -> pd.Series:
        return sma(close, period)


@dataclass(frozen=True)
class _EmaCross(_MovingAverageCross):
    fast: int = 9
    slow: int = 21

    def _average(self, close: pd.Series, period: int) -> pd.Series:
        return ema(close, period)


@register
class GoldenCross(_SmaCross):
    name = "golden_cross"
    direction = Direction.LONG
    description = "SMA(50) crosses above SMA(200)"


@register
class DeathCross(_SmaCross):
    name = "death_cross"
    direction = Direction.SHORT
    description = "SMA(50) crosses below SMA(200)"


@register
class EmaCrossUp(_EmaCross):
    name = "ema_cross_up"
    direction = Direction.LONG
    description = "EMA(9) crosses above EMA(21)"


@register
class EmaCrossDown(_EmaCross):
    name = "ema_cross_down"
    direction = Direction.SHORT
    description = "EMA(9) crosses below EMA(21)"


@dataclass(frozen=True)
class _SupertrendFlip(Signal):
    period: int = 10
    mult: float = 3.0
    family = Family.TREND

    def condition(self, df: pd.DataFrame) -> pd.Series:
        trend = supertrend(df, self.period, self.mult)["direction"]
        wanted = self.direction.sign
        return (trend == wanted) & (trend.shift(1) == -wanted)


@register
class SupertrendUp(_SupertrendFlip):
    name = "supertrend_up"
    direction = Direction.LONG
    description = "Supertrend(10, 3) flips from down to up"


@register
class SupertrendDown(_SupertrendFlip):
    name = "supertrend_down"
    direction = Direction.SHORT
    description = "Supertrend(10, 3) flips from up to down"


@dataclass(frozen=True)
class _AdxDiCross(Signal):
    period: int = 14
    min_adx: float = 20.0
    family = Family.TREND

    def condition(self, df: pd.DataFrame) -> pd.Series:
        frame = adx(df, self.period)
        leader, other = (
            (frame["plus_di"], frame["minus_di"])
            if self.direction is Direction.LONG
            else (frame["minus_di"], frame["plus_di"])
        )
        return crossed_above(leader, other) & (frame["adx"] >= self.min_adx)


@register
class AdxDiUp(_AdxDiCross):
    name = "adx_di_up"
    direction = Direction.LONG
    description = "+DI crosses above -DI while ADX(14) >= 20"


@register
class AdxDiDown(_AdxDiCross):
    name = "adx_di_down"
    direction = Direction.SHORT
    description = "-DI crosses above +DI while ADX(14) >= 20"
