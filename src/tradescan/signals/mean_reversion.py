"""Mean-reversion signals."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass

import pandas as pd

from tradescan.indicators import bollinger, rsi, sma
from tradescan.params import param
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.conditions import crossed_above, crossed_below
from tradescan.signals.registry import register


@dataclass(frozen=True)
class _ConnorsRsi2(Signal):
    rsi_period: int = param(2, minimum=2, maximum=30, step=1, label="RSI period", unit="bars")
    trend_period: int = param(200, minimum=10, maximum=400, step=1, label="Trend SMA", unit="bars")
    family = Family.MEAN_REVERSION

    def condition(self, df: pd.DataFrame) -> pd.Series:
        return self._fires(rsi(df["close"], self.rsi_period), df["close"], sma(df["close"], self.trend_period))

    @abstractmethod
    def _fires(self, values: pd.Series, close: pd.Series, trend: pd.Series) -> pd.Series: ...


@register
@dataclass(frozen=True)
class ConnorsRsi2Long(_ConnorsRsi2):
    oversold: float = param(10.0, minimum=1.0, maximum=50.0, step=1.0, label="Oversold level")
    name = "connors_rsi2_long"
    direction = Direction.LONG
    description = "RSI({rsi_period}) < {oversold:g} while price is above SMA({trend_period}): dip in an uptrend"

    def _fires(self, values: pd.Series, close: pd.Series, trend: pd.Series) -> pd.Series:
        return (values < self.oversold) & (close > trend)


@register
@dataclass(frozen=True)
class ConnorsRsi2Short(_ConnorsRsi2):
    overbought: float = param(90.0, minimum=50.0, maximum=99.0, step=1.0, label="Overbought level")
    name = "connors_rsi2_short"
    direction = Direction.SHORT
    description = "RSI({rsi_period}) > {overbought:g} while price is below SMA({trend_period}): bounce in a downtrend"

    def _fires(self, values: pd.Series, close: pd.Series, trend: pd.Series) -> pd.Series:
        return (values > self.overbought) & (close < trend)


@dataclass(frozen=True)
class _BollingerReentry(Signal):
    period: int = param(20, minimum=5, maximum=100, step=1, label="Band length", unit="bars")
    mult: float = param(2.0, minimum=0.5, maximum=5.0, step=0.1, label="Band width", unit="std")
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
    description = "Close returns above the lower Bollinger Band({period}, {mult:g})"


@register
class BollingerReentryDown(_BollingerReentry):
    name = "bb_reentry_down"
    direction = Direction.SHORT
    description = "Close returns below the upper Bollinger Band({period}, {mult:g})"
