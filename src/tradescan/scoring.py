"""Confluence score: weighted fresh signals plus trend and relative-strength alignment."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from tradescan.context import TickerContext, Trend
from tradescan.signals.base import Direction, Signal


@dataclass(frozen=True)
class ScoreBreakdown:
    signals: float
    trend: float
    weekly: float
    relative_strength: float

    @property
    def total(self) -> float:
        return self.signals + self.trend + self.weekly + self.relative_strength


class Scorer:
    def __init__(
        self,
        family_weights: Mapping[str, float],
        signal_weights: Mapping[str, float],
        trend_bonus: float = 1.0,
        weekly_bonus: float = 1.0,
        rs_bonus: float = 1.0,
        rs_strong_pct: float = 80.0,
    ) -> None:
        self._family_weights = dict(family_weights)
        self._signal_weights = dict(signal_weights)
        self._trend_bonus = trend_bonus
        self._weekly_bonus = weekly_bonus
        self._rs_bonus = rs_bonus
        self._rs_strong_pct = rs_strong_pct

    def weight(self, signal: Signal) -> float:
        """Per-signal override, else the family weight, else 1.0."""
        return self._signal_weights.get(signal.name, self._family_weights.get(signal.family.value, 1.0))

    def score(
        self,
        direction: Direction,
        signals: Sequence[Signal],
        context: TickerContext,
        rs_percentile: float,
    ) -> ScoreBreakdown:
        return ScoreBreakdown(
            signals=sum(self.weight(signal) for signal in signals),
            trend=self._alignment(direction, context.daily_trend, self._trend_bonus),
            weekly=self._alignment(direction, context.weekly_trend, self._weekly_bonus),
            relative_strength=self._relative_strength(direction, rs_percentile),
        )

    @staticmethod
    def _alignment(direction: Direction, trend: Trend, bonus: float) -> float:
        if trend is Trend.NEUTRAL:
            return 0.0
        agrees = (trend is Trend.UP) == (direction is Direction.LONG)
        return bonus if agrees else -bonus

    def _relative_strength(self, direction: Direction, percentile: float) -> float:
        if math.isnan(percentile):
            return 0.0
        if direction is Direction.LONG:
            return self._rs_bonus if percentile >= self._rs_strong_pct else 0.0
        return self._rs_bonus if percentile <= 100.0 - self._rs_strong_pct else 0.0

    def bar_scores(
        self,
        direction: Direction,
        signal_points: np.ndarray,
        daily_trend: np.ndarray,
        weekly_trend: np.ndarray,
        rs_percentile: np.ndarray,
    ) -> np.ndarray:
        """The total score at every bar, from each bar's signal points (the weights of the fresh signals), its
        trends as 1 (up), -1 (down) or 0 (neutral) and its RS percentile (NaN for none)."""
        if direction is Direction.LONG:
            strong = rs_percentile >= self._rs_strong_pct  # NaN compares false
        else:
            strong = rs_percentile <= 100.0 - self._rs_strong_pct
        return (
            signal_points
            + self._trend_bonus * direction.sign * daily_trend
            + self._weekly_bonus * direction.sign * weekly_trend
            + np.where(strong, self._rs_bonus, 0.0)
        )
