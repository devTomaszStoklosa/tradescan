"""Entry filters: conditions a signal has to meet at the close of its bar before it may place its order.

A filter computes once per run, for every bar, whether a signal at that close may trade. Every chosen
filter has to allow a signal; a blocked signal is ignored and does not carry over to a later bar. Bars
where a filter's indicator is still warming up block signals. Shorts mirror longs. New filters plug in
with `@entry_filters.register`.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import ClassVar

import numpy as np
import pandas as pd

from tradescan.backtest.rules import Bars, Rule, RuleRegistry
from tradescan.indicators import adx, relative_volume, sma
from tradescan.params import param
from tradescan.signals.base import Direction


@dataclass(frozen=True, eq=False)
class FilterInputs:
    """What the filters read: the ticker's bars and, for filters that compare the market, the benchmark's closes."""

    bars: Bars
    benchmark_close: pd.Series | None = None  # on the benchmark's own dates


class EntryFilter(Rule):
    needs_benchmark: ClassVar[bool] = False  # True when `allows` reads the benchmark's closes

    @abstractmethod
    def allows(self, inputs: FilterInputs, direction: Direction) -> np.ndarray:
        """Causal booleans: True where a signal at the close of that bar may place its order."""


entry_filters: RuleRegistry[EntryFilter] = RuleRegistry("filter")


def _beyond(values: pd.Series, average: pd.Series, sign: float) -> pd.Series:
    """True where `values` is above `average` for a sign of +1, below it for -1; False while the average is NaN."""
    return sign * (values - average) > 0


@entry_filters.register
@dataclass(frozen=True)
class TrendFilter(EntryFilter):
    period: int = param(200, minimum=2, maximum=400, step=1, label="SMA length", unit="bars")
    name = "trend"
    label = "Trend filter"
    description = "Close above SMA({period}) for longs, below it for shorts"

    def allows(self, inputs: FilterInputs, direction: Direction) -> np.ndarray:
        close = pd.Series(inputs.bars.close)
        return _beyond(close, sma(close, self.period), direction.sign).to_numpy(dtype=bool)


@entry_filters.register
@dataclass(frozen=True)
class MarketFilter(EntryFilter):
    period: int = param(
        200,
        minimum=2,
        maximum=400,
        step=1,
        label="Benchmark SMA",
        unit="bars",
        help="Counted in the benchmark's own bars",
    )
    name = "market"
    label = "Market filter"
    description = "Benchmark close above its SMA({period}) for longs, below it for shorts"
    needs_benchmark = True

    def allows(self, inputs: FilterInputs, direction: Direction) -> np.ndarray:
        if inputs.benchmark_close is None:
            raise ValueError(f"The {self.name} filter needs the benchmark's closes")
        close = inputs.benchmark_close.astype(float)
        beyond = _beyond(close, sma(close, self.period), direction.sign).astype(float)
        # Each ticker date gets the benchmark's last close at or before it; dates before its first bar block.
        aligned = beyond.reindex(inputs.bars.dates, method="ffill")
        return (aligned == 1.0).to_numpy(dtype=bool)


@entry_filters.register
@dataclass(frozen=True)
class AdxFilter(EntryFilter):
    period: int = param(14, minimum=2, maximum=100, step=1, label="ADX period", unit="bars")
    min_adx: float = param(20.0, minimum=1.0, maximum=100.0, step=1.0, label="Minimum ADX")
    name = "adx"
    label = "ADX filter"
    description = "ADX({period}) at or above {min_adx:g}"

    def allows(self, inputs: FilterInputs, direction: Direction) -> np.ndarray:
        bars = inputs.bars
        frame = pd.DataFrame({"high": bars.high, "low": bars.low, "close": bars.close})
        return (adx(frame, self.period)["adx"] >= self.min_adx).to_numpy(dtype=bool)


@entry_filters.register
@dataclass(frozen=True)
class VolumeFilter(EntryFilter):
    period: int = param(
        20, minimum=2, maximum=250, step=1, label="Average over", unit="bars", help="The bars before the signal bar"
    )
    min_ratio: float = param(
        1.5,
        minimum=0.1,
        maximum=20.0,
        step=0.1,
        label="Minimum volume",
        unit="× average",
        help="Tickers without volume (indices, some FX) never pass",
    )
    name = "volume"
    label = "Volume filter"
    description = "Volume at least {min_ratio:g} times the average of the previous {period} bars"

    def allows(self, inputs: FilterInputs, direction: Direction) -> np.ndarray:
        ratio = relative_volume(pd.Series(inputs.bars.volume), self.period)
        return (ratio >= self.min_ratio).to_numpy(dtype=bool)


@entry_filters.register
@dataclass(frozen=True)
class AtrPercentFilter(EntryFilter):
    min_pct: float = param(
        1.0,
        minimum=0.0,
        maximum=100.0,
        step=0.1,
        label="Minimum",
        unit="% of close",
        help="ATR of the risk settings' period",
    )
    max_pct: float = param(5.0, minimum=0.1, maximum=100.0, step=0.1, label="Maximum", unit="% of close")
    name = "atr_pct"
    label = "ATR% band"
    description = "ATR between {min_pct:g}% and {max_pct:g}% of the close"

    def __post_init__(self) -> None:
        if self.min_pct >= self.max_pct:
            raise ValueError(
                f"{self.name}: the minimum ({self.min_pct:g}%) must be below the maximum ({self.max_pct:g}%)"
            )

    def allows(self, inputs: FilterInputs, direction: Direction) -> np.ndarray:
        bars = inputs.bars
        with np.errstate(divide="ignore", invalid="ignore"):
            pct = 100.0 * bars.atr / bars.close
        allowed: np.ndarray = (pct >= self.min_pct) & (pct <= self.max_pct)
        return allowed
