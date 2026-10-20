"""Mean-reversion signals."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass

import pandas as pd

from tradescan.indicators import bollinger, internal_bar_strength, percent_b, rsi, sma
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


@dataclass(frozen=True)
class _InternalBarStrength(Signal):
    zone: float = param(
        0.2,
        minimum=0.01,
        maximum=0.5,
        step=0.01,
        label="Close zone",
        help="Share of the bar's range at its low (long) or its high (short)",
    )
    family = Family.MEAN_REVERSION

    def condition(self, df: pd.DataFrame) -> pd.Series:
        strength = internal_bar_strength(df)
        if self.direction is Direction.LONG:
            return strength < self.zone
        return strength > 1.0 - self.zone


@register
class InternalBarStrengthLow(_InternalBarStrength):
    name = "ibs_low"
    direction = Direction.LONG
    description = "Close in the bottom {zone:.0%} of the bar's range (internal bar strength)"


@register
class InternalBarStrengthHigh(_InternalBarStrength):
    name = "ibs_high"
    direction = Direction.SHORT
    description = "Close in the top {zone:.0%} of the bar's range (internal bar strength)"


@dataclass(frozen=True)
class _CloseStreak(Signal):
    bars: int = param(3, minimum=2, maximum=10, step=1, label="Closes in a row", unit="bars")
    family = Family.MEAN_REVERSION

    def condition(self, df: pd.DataFrame) -> pd.Series:
        change = df["close"].diff()
        moved = change < 0 if self.direction is Direction.LONG else change > 0
        return moved.astype(int).rolling(self.bars, min_periods=self.bars).sum() == self.bars


@register
class DownStreak(_CloseStreak):
    name = "down_streak"
    direction = Direction.LONG
    description = "{bars} lower closes in a row"


@register
class UpStreak(_CloseStreak):
    name = "up_streak"
    direction = Direction.SHORT
    description = "{bars} higher closes in a row"


@dataclass(frozen=True)
class _CumulativeRsi(Signal):
    rsi_period: int = param(2, minimum=2, maximum=30, step=1, label="RSI period", unit="bars")
    bars: int = param(2, minimum=2, maximum=10, step=1, label="Summed bars", unit="bars")
    family = Family.MEAN_REVERSION

    def __post_init__(self) -> None:
        ceiling = 100 * self.bars
        if self._level() >= ceiling:
            raise ValueError(
                f"{self.name}: the level ({self._level():g}) must be below {ceiling}, "
                f"the most RSI summed over {self.bars} bars can reach"
            )

    def condition(self, df: pd.DataFrame) -> pd.Series:
        total = rsi(df["close"], self.rsi_period).rolling(self.bars, min_periods=self.bars).sum()
        return self._fires(total)

    @abstractmethod
    def _level(self) -> float: ...

    @abstractmethod
    def _fires(self, total: pd.Series) -> pd.Series: ...


@register
@dataclass(frozen=True)
class CumulativeRsiLong(_CumulativeRsi):
    oversold: float = param(35.0, minimum=1.0, maximum=999.0, step=1.0, label="Sum below")
    name = "cumulative_rsi_long"
    direction = Direction.LONG
    description = "RSI({rsi_period}) summed over {bars} bars < {oversold:g}"

    def _level(self) -> float:
        return self.oversold

    def _fires(self, total: pd.Series) -> pd.Series:
        return total < self.oversold


@register
@dataclass(frozen=True)
class CumulativeRsiShort(_CumulativeRsi):
    overbought: float = param(165.0, minimum=1.0, maximum=999.0, step=1.0, label="Sum above")
    name = "cumulative_rsi_short"
    direction = Direction.SHORT
    description = "RSI({rsi_period}) summed over {bars} bars > {overbought:g}"

    def _level(self) -> float:
        return self.overbought

    def _fires(self, total: pd.Series) -> pd.Series:
        return total > self.overbought


@dataclass(frozen=True)
class _PercentB(Signal):
    period: int = param(20, minimum=5, maximum=100, step=1, label="Band length", unit="bars")
    mult: float = param(2.0, minimum=0.5, maximum=5.0, step=0.1, label="Band width", unit="std")
    family = Family.MEAN_REVERSION

    def condition(self, df: pd.DataFrame) -> pd.Series:
        return self._fires(percent_b(df["close"], self.period, self.mult))

    @abstractmethod
    def _fires(self, values: pd.Series) -> pd.Series: ...


@register
@dataclass(frozen=True)
class PercentBLow(_PercentB):
    below: float = param(
        0.0, minimum=-1.0, maximum=0.5, step=0.05, label="%b below", help="0 is the lower band, 1 the upper"
    )
    name = "bb_pctb_low"
    direction = Direction.LONG
    description = "Bollinger %b({period}, {mult:g}) < {below:g} (0 = lower band)"

    def _fires(self, values: pd.Series) -> pd.Series:
        return values < self.below


@register
@dataclass(frozen=True)
class PercentBHigh(_PercentB):
    above: float = param(
        1.0, minimum=0.5, maximum=2.0, step=0.05, label="%b above", help="0 is the lower band, 1 the upper"
    )
    name = "bb_pctb_high"
    direction = Direction.SHORT
    description = "Bollinger %b({period}, {mult:g}) > {above:g} (1 = upper band)"

    def _fires(self, values: pd.Series) -> pd.Series:
        return values > self.above
