"""Momentum signals."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass

import pandas as pd

from tradescan.indicators import macd, rsi
from tradescan.params import param
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.conditions import crossed_above, crossed_below
from tradescan.signals.registry import register


@dataclass(frozen=True)
class _MacdCross(Signal):
    fast: int = param(12, minimum=2, maximum=100, step=1, label="Fast EMA", unit="bars")
    slow: int = param(26, minimum=3, maximum=200, step=1, label="Slow EMA", unit="bars")
    signal: int = param(9, minimum=2, maximum=100, step=1, label="Signal line", unit="bars")
    family = Family.MOMENTUM

    def __post_init__(self) -> None:
        if self.fast >= self.slow:
            raise ValueError(f"{self.name}: the fast EMA ({self.fast}) must be shorter than the slow EMA ({self.slow})")

    def condition(self, df: pd.DataFrame) -> pd.Series:
        frame = macd(df["close"], self.fast, self.slow, self.signal)
        cross = crossed_above if self.direction is Direction.LONG else crossed_below
        return cross(frame["macd"], frame["signal"])


@register
class MacdCrossUp(_MacdCross):
    name = "macd_cross_up"
    direction = Direction.LONG
    description = "MACD({fast}, {slow}) crosses above its {signal}-period signal line"


@register
class MacdCrossDown(_MacdCross):
    name = "macd_cross_down"
    direction = Direction.SHORT
    description = "MACD({fast}, {slow}) crosses below its {signal}-period signal line"


@dataclass(frozen=True)
class _RsiReversal(Signal):
    period: int = param(14, minimum=2, maximum=100, step=1, label="RSI period", unit="bars")
    family = Family.MOMENTUM

    def condition(self, df: pd.DataFrame) -> pd.Series:
        return self._crosses(rsi(df["close"], self.period))

    @abstractmethod
    def _crosses(self, values: pd.Series) -> pd.Series: ...


@register
@dataclass(frozen=True)
class RsiReversalUp(_RsiReversal):
    oversold: float = param(30.0, minimum=1.0, maximum=50.0, step=1.0, label="Oversold level")
    name = "rsi_reversal_up"
    direction = Direction.LONG
    description = "RSI({period}) climbs back above {oversold:g}"

    def _crosses(self, values: pd.Series) -> pd.Series:
        return crossed_above(values, self.oversold)


@register
@dataclass(frozen=True)
class RsiReversalDown(_RsiReversal):
    overbought: float = param(70.0, minimum=50.0, maximum=99.0, step=1.0, label="Overbought level")
    name = "rsi_reversal_down"
    direction = Direction.SHORT
    description = "RSI({period}) drops back below {overbought:g}"

    def _crosses(self, values: pd.Series) -> pd.Series:
        return crossed_below(values, self.overbought)
