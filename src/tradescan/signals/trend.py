"""Trend-following signals."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass

import pandas as pd

from tradescan.indicators import adx, ema, sma, supertrend
from tradescan.params import param
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.conditions import crossed_above, crossed_below
from tradescan.signals.registry import register


@dataclass(frozen=True)
class _MovingAverageCross(Signal):
    fast: int
    slow: int
    family = Family.TREND

    def __post_init__(self) -> None:
        if self.fast >= self.slow:
            raise ValueError(
                f"{self.name}: the fast average ({self.fast}) must be shorter than the slow one ({self.slow})"
            )

    @abstractmethod
    def _average(self, close: pd.Series, period: int) -> pd.Series: ...

    def condition(self, df: pd.DataFrame) -> pd.Series:
        fast = self._average(df["close"], self.fast)
        slow = self._average(df["close"], self.slow)
        cross = crossed_above if self.direction is Direction.LONG else crossed_below
        return cross(fast, slow)


@dataclass(frozen=True)
class _SmaCross(_MovingAverageCross):
    fast: int = param(50, minimum=2, maximum=400, step=1, label="Fast SMA", unit="bars")
    slow: int = param(200, minimum=3, maximum=500, step=1, label="Slow SMA", unit="bars")

    def _average(self, close: pd.Series, period: int) -> pd.Series:
        return sma(close, period)


@dataclass(frozen=True)
class _EmaCross(_MovingAverageCross):
    fast: int = param(9, minimum=2, maximum=200, step=1, label="Fast EMA", unit="bars")
    slow: int = param(21, minimum=3, maximum=400, step=1, label="Slow EMA", unit="bars")

    def _average(self, close: pd.Series, period: int) -> pd.Series:
        return ema(close, period)


@register
class GoldenCross(_SmaCross):
    name = "golden_cross"
    direction = Direction.LONG
    description = "SMA({fast}) crosses above SMA({slow})"


@register
class DeathCross(_SmaCross):
    name = "death_cross"
    direction = Direction.SHORT
    description = "SMA({fast}) crosses below SMA({slow})"


@register
class EmaCrossUp(_EmaCross):
    name = "ema_cross_up"
    direction = Direction.LONG
    description = "EMA({fast}) crosses above EMA({slow})"


@register
class EmaCrossDown(_EmaCross):
    name = "ema_cross_down"
    direction = Direction.SHORT
    description = "EMA({fast}) crosses below EMA({slow})"


@dataclass(frozen=True)
class _SupertrendFlip(Signal):
    period: int = param(10, minimum=2, maximum=100, step=1, label="ATR period", unit="bars")
    mult: float = param(3.0, minimum=0.5, maximum=10.0, step=0.1, label="ATR multiple")
    family = Family.TREND

    def condition(self, df: pd.DataFrame) -> pd.Series:
        trend = supertrend(df, self.period, self.mult)["direction"]
        wanted = self.direction.sign
        return (trend == wanted) & (trend.shift(1) == -wanted)


@register
class SupertrendUp(_SupertrendFlip):
    name = "supertrend_up"
    direction = Direction.LONG
    description = "Supertrend({period}, {mult:g}) flips from down to up"


@register
class SupertrendDown(_SupertrendFlip):
    name = "supertrend_down"
    direction = Direction.SHORT
    description = "Supertrend({period}, {mult:g}) flips from up to down"


@dataclass(frozen=True)
class _AdxDiCross(Signal):
    period: int = param(14, minimum=2, maximum=100, step=1, label="ADX period", unit="bars")
    min_adx: float = param(20.0, minimum=0.0, maximum=100.0, step=1.0, label="Minimum ADX")
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
    description = "+DI crosses above -DI while ADX({period}) >= {min_adx:g}"


@register
class AdxDiDown(_AdxDiCross):
    name = "adx_di_down"
    direction = Direction.SHORT
    description = "-DI crosses above +DI while ADX({period}) >= {min_adx:g}"
