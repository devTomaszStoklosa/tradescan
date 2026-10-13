"""Volume-based signals."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from tradescan.indicators import relative_volume, sma
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.registry import register


@dataclass(frozen=True)
class _VolumeClimax(Signal):
    rvol_period: int = 20
    min_rvol: float = 2.0
    close_location: float = 0.75
    family = Family.VOLUME

    def condition(self, df: pd.DataFrame) -> pd.Series:
        rvol = relative_volume(df["volume"], self.rvol_period)
        bar_range = (df["high"] - df["low"]).replace(0.0, np.nan)
        location = (df["close"] - df["low"]) / bar_range  # 0 = closed at the low, 1 = at the high
        previous_close = df["close"].shift(1)
        heavy = rvol >= self.min_rvol
        if self.direction is Direction.LONG:
            return heavy & (location >= self.close_location) & (df["close"] > previous_close)
        return heavy & (location <= 1.0 - self.close_location) & (df["close"] < previous_close)


@register
class VolumeSpikeUp(_VolumeClimax):
    name = "volume_spike_up"
    direction = Direction.LONG
    description = "Up day on >= 2x average volume closing in the top quarter of its range (accumulation)"


@register
class DistributionDay(_VolumeClimax):
    name = "distribution_day"
    direction = Direction.SHORT
    description = "Down day on >= 2x average volume closing in the bottom quarter of its range"


@register
@dataclass(frozen=True)
class PocketPivot(Signal):
    lookback: int = 10
    trend_period: int = 50
    name = "pocket_pivot"
    family = Family.VOLUME
    direction = Direction.LONG
    description = "Up-day volume above every down-day volume of the prior 10 bars, price above SMA(50)"

    def condition(self, df: pd.DataFrame) -> pd.Series:
        close, volume = df["close"], df["volume"]
        down_volume = volume.where(close < close.shift(1), 0.0)
        max_down_volume = down_volume.rolling(self.lookback, min_periods=self.lookback).max().shift(1)
        return (close > close.shift(1)) & (volume > max_down_volume) & (close > sma(close, self.trend_period))
