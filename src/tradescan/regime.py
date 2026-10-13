"""Market regime: benchmark trend plus breadth of the watchlist."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

from tradescan.indicators import sma


class Regime(StrEnum):
    RISK_ON = "risk-on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk-off"


@dataclass(frozen=True)
class MarketRegime:
    benchmark: str
    benchmark_close: float
    benchmark_above_slow: bool | None
    benchmark_fast_above_slow: bool | None
    pct_above_fast: float
    pct_above_slow: float
    new_highs: int
    new_lows: int
    universe_size: int
    regime: Regime


class MarketRegimeAnalyzer:
    def __init__(
        self,
        fast_period: int = 50,
        slow_period: int = 200,
        high_low_period: int = 252,
        risk_on_breadth: float = 60.0,
        risk_off_breadth: float = 40.0,
    ) -> None:
        self._fast = fast_period
        self._slow = slow_period
        self._high_low = high_low_period
        self._risk_on_breadth = risk_on_breadth
        self._risk_off_breadth = risk_off_breadth

    def analyze(
        self,
        benchmark: str,
        benchmark_df: pd.DataFrame | None,
        universe: Mapping[str, pd.DataFrame],
    ) -> MarketRegime:
        above_slow, fast_above_slow, last_close = self._benchmark_trend(benchmark_df)
        pct_fast = self._pct_above(universe, self._fast)
        pct_slow = self._pct_above(universe, self._slow)
        new_highs = sum(df["high"].iloc[-1] >= df["high"].iloc[-self._high_low :].max() for df in universe.values())
        new_lows = sum(df["low"].iloc[-1] <= df["low"].iloc[-self._high_low :].min() for df in universe.values())
        return MarketRegime(
            benchmark=benchmark,
            benchmark_close=last_close,
            benchmark_above_slow=above_slow,
            benchmark_fast_above_slow=fast_above_slow,
            pct_above_fast=pct_fast,
            pct_above_slow=pct_slow,
            new_highs=int(new_highs),
            new_lows=int(new_lows),
            universe_size=len(universe),
            regime=self._classify(above_slow, pct_fast),
        )

    def _benchmark_trend(self, df: pd.DataFrame | None) -> tuple[bool | None, bool | None, float]:
        if df is None or df.empty:
            return None, None, math.nan
        close = df["close"]
        fast, slow = sma(close, self._fast).iloc[-1], sma(close, self._slow).iloc[-1]
        last = float(close.iloc[-1])
        if pd.isna(slow):
            return None, None, last
        return bool(last > slow), bool(fast > slow), last

    @staticmethod
    def _pct_above(universe: Mapping[str, pd.DataFrame], period: int) -> float:
        flags = [
            bool(df["close"].iloc[-1] > average)
            for df in universe.values()
            if not pd.isna(average := sma(df["close"], period).iloc[-1])
        ]
        return 100.0 * sum(flags) / len(flags) if flags else math.nan

    def _classify(self, benchmark_above_slow: bool | None, pct_above_fast: float) -> Regime:
        if math.isnan(pct_above_fast):
            return Regime.NEUTRAL
        strong_breadth = pct_above_fast >= self._risk_on_breadth
        weak_breadth = pct_above_fast <= self._risk_off_breadth
        if benchmark_above_slow is None:
            return Regime.RISK_ON if strong_breadth else Regime.RISK_OFF if weak_breadth else Regime.NEUTRAL
        if benchmark_above_slow and strong_breadth:
            return Regime.RISK_ON
        if not benchmark_above_slow and weak_breadth:
            return Regime.RISK_OFF
        return Regime.NEUTRAL
