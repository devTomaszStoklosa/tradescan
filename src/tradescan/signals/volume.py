"""Volume-based signals."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass

import numpy as np
import pandas as pd

from tradescan.indicators import relative_volume, sma
from tradescan.params import param
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.registry import register


@dataclass(frozen=True)
class _VolumeClimax(Signal):
    rvol_period: int = param(20, minimum=5, maximum=200, step=1, label="Volume average", unit="bars")
    min_rvol: float = param(2.0, minimum=0.5, maximum=10.0, step=0.1, label="Minimum relative volume", unit="x")
    family = Family.VOLUME

    def condition(self, df: pd.DataFrame) -> pd.Series:
        rvol = relative_volume(df["volume"], self.rvol_period)
        bar_range = (df["high"] - df["low"]).replace(0.0, np.nan)
        location = (df["close"] - df["low"]) / bar_range  # 0 = closed at the low, 1 = at the high
        return (rvol >= self.min_rvol) & self._fires(location, df["close"], df["close"].shift(1))

    @abstractmethod
    def _fires(self, location: pd.Series, close: pd.Series, previous_close: pd.Series) -> pd.Series: ...


@register
@dataclass(frozen=True)
class VolumeSpikeUp(_VolumeClimax):
    min_close_location: float = param(
        0.75, minimum=0.5, maximum=1.0, step=0.05, label="Close at or above", help="0 = the bar's low, 1 = its high"
    )
    name = "volume_spike_up"
    direction = Direction.LONG
    description = (
        "Up day on >= {min_rvol:g}x the {rvol_period}-bar average volume, closing at or above "
        "{min_close_location:.0%} of its range (accumulation)"
    )

    def _fires(self, location: pd.Series, close: pd.Series, previous_close: pd.Series) -> pd.Series:
        return (location >= self.min_close_location) & (close > previous_close)


@register
@dataclass(frozen=True)
class DistributionDay(_VolumeClimax):
    max_close_location: float = param(
        0.25, minimum=0.0, maximum=0.5, step=0.05, label="Close at or below", help="0 = the bar's low, 1 = its high"
    )
    name = "distribution_day"
    direction = Direction.SHORT
    description = (
        "Down day on >= {min_rvol:g}x the {rvol_period}-bar average volume, closing at or below "
        "{max_close_location:.0%} of its range"
    )

    def _fires(self, location: pd.Series, close: pd.Series, previous_close: pd.Series) -> pd.Series:
        return (location <= self.max_close_location) & (close < previous_close)


@register
@dataclass(frozen=True)
class PocketPivot(Signal):
    lookback: int = param(10, minimum=2, maximum=50, step=1, label="Down-volume lookback", unit="bars")
    trend_period: int = param(50, minimum=5, maximum=400, step=1, label="Trend SMA", unit="bars")
    name = "pocket_pivot"
    family = Family.VOLUME
    direction = Direction.LONG
    description = (
        "Up-day volume above every down-day volume of the prior {lookback} bars, price above SMA({trend_period})"
    )

    def condition(self, df: pd.DataFrame) -> pd.Series:
        close, volume = df["close"], df["volume"]
        down_volume = volume.where(close < close.shift(1), 0.0)
        max_down_volume = down_volume.rolling(self.lookback, min_periods=self.lookback).max().shift(1)
        return (close > close.shift(1)) & (volume > max_down_volume) & (close > sma(close, self.trend_period))
