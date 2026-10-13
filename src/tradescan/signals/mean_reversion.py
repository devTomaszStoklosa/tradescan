"""Mean-reversion signals."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradescan.indicators import bollinger, rsi, sma
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.conditions import crossed_above, crossed_below
from tradescan.signals.registry import register


@dataclass(frozen=True)
class _ConnorsRsi2(Signal):
    rsi_period: int = 2
    trend_period: int = 200
    oversold: float = 10.0
    overbought: float = 90.0
    family = Family.MEAN_REVERSION

    def condition(self, df: pd.DataFrame) -> pd.Series:
        values = rsi(df["close"], self.rsi_period)
        trend = sma(df["close"], self.trend_period)
        if self.direction is Direction.LONG:
            return (values < self.oversold) & (df["close"] > trend)
        return (values > self.overbought) & (df["close"] < trend)


@register
class ConnorsRsi2Long(_ConnorsRsi2):
    name = "connors_rsi2_long"
    direction = Direction.LONG
    description = "RSI(2) < 10 while price is above SMA(200): dip in an uptrend"


@register
class ConnorsRsi2Short(_ConnorsRsi2):
    name = "connors_rsi2_short"
    direction = Direction.SHORT
    description = "RSI(2) > 90 while price is below SMA(200): bounce in a downtrend"


@dataclass(frozen=True)
class _BollingerReentry(Signal):
    period: int = 20
    mult: float = 2.0
    family = Family.MEAN_REVERSION

    def condition(self, df: pd.DataFrame) -> pd.Series:
        bands = bollinger(df["close"], self.period, self.mult)
        if self.direction is Direction.LONG:
            return crossed_above(df["close"], bands["lower"])
        return crossed_below(df["close"], bands["upper"])


@register
class BollingerReentryUp(_BollingerReentry):
    name = "bb_reentry_up"
    direction = Direction.LONG
    description = "Close returns above the lower Bollinger Band(20, 2)"


@register
class BollingerReentryDown(_BollingerReentry):
    name = "bb_reentry_down"
    direction = Direction.SHORT
    description = "Close returns below the upper Bollinger Band(20, 2)"
