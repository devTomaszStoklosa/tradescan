"""Momentum signals."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradescan.indicators import macd, rsi
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.conditions import crossed_above, crossed_below
from tradescan.signals.registry import register


@dataclass(frozen=True)
class _MacdCross(Signal):
    fast: int = 12
    slow: int = 26
    signal: int = 9
    family = Family.MOMENTUM

    def condition(self, df: pd.DataFrame) -> pd.Series:
        frame = macd(df["close"], self.fast, self.slow, self.signal)
        cross = crossed_above if self.direction is Direction.LONG else crossed_below
        return cross(frame["macd"], frame["signal"])


@register
class MacdCrossUp(_MacdCross):
    name = "macd_cross_up"
    direction = Direction.LONG
    description = "MACD(12, 26) crosses above its 9-period signal line"


@register
class MacdCrossDown(_MacdCross):
    name = "macd_cross_down"
    direction = Direction.SHORT
    description = "MACD(12, 26) crosses below its 9-period signal line"


@dataclass(frozen=True)
class _RsiReversal(Signal):
    period: int = 14
    oversold: float = 30.0
    overbought: float = 70.0
    family = Family.MOMENTUM

    def condition(self, df: pd.DataFrame) -> pd.Series:
        values = rsi(df["close"], self.period)
        if self.direction is Direction.LONG:
            return crossed_above(values, self.oversold)
        return crossed_below(values, self.overbought)


@register
class RsiReversalUp(_RsiReversal):
    name = "rsi_reversal_up"
    direction = Direction.LONG
    description = "RSI(14) climbs back above 30"


@register
class RsiReversalDown(_RsiReversal):
    name = "rsi_reversal_down"
    direction = Direction.SHORT
    description = "RSI(14) drops back below 70"
