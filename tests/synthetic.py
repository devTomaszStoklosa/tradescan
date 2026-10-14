"""Deterministic synthetic market data and test doubles shared by the tests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

import numpy as np
import pandas as pd

from tradescan.backtest.exits import ExitOrders, ExitRule, TrackerFactory
from tradescan.backtest.rules import Bars
from tradescan.signals.base import Direction, Family, Signal


def make_ohlcv(
    close: Sequence[float],
    opens: Sequence[float] | None = None,
    spread: float = 0.01,
    volume: float | Sequence[float] = 1_000_000.0,
    start: str = "2015-01-01",
) -> pd.DataFrame:
    """Bars whose open is the previous close (unless given) and whose range is `spread` around the body."""
    close_values = np.asarray(close, dtype=float)
    open_values = np.r_[close_values[0], close_values[:-1]] if opens is None else np.asarray(opens, dtype=float)
    volume_values = np.full(len(close_values), float(volume)) if np.isscalar(volume) else np.asarray(volume, float)
    index = pd.bdate_range(start, periods=len(close_values), name="date")
    return pd.DataFrame(
        {
            "open": open_values,
            "high": np.maximum(open_values, close_values) * (1 + spread),
            "low": np.minimum(open_values, close_values) * (1 - spread),
            "close": close_values,
            "volume": volume_values,
        },
        index=index,
    )


def random_walk(bars: int = 3000, seed: int = 7, drift: float = 0.0002, volatility: float = 0.018) -> pd.DataFrame:
    """Random walk with volatility regimes, occasional gaps and lognormal volume, so every signal fires."""
    rng = np.random.default_rng(seed)
    regime = np.repeat(rng.choice([0.5, 1.0, 2.0], size=bars // 50 + 1), 50)[:bars]
    trend = np.repeat(rng.normal(0, 0.002, size=bars // 120 + 1), 120)[:bars]
    gaps = rng.normal(0, volatility / 3, bars)
    gaps[rng.random(bars) < 0.03] *= 8
    intraday = rng.normal(drift, volatility, bars) * regime + trend
    close = 100.0 * np.exp(np.cumsum(gaps + intraday))
    open_ = close * np.exp(-intraday)
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, volatility / 2, bars)) * regime)
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, volatility / 2, bars)) * regime)
    # Like real markets, volume rises on big moves and gaps.
    volume = rng.lognormal(13, 0.4, bars) * (1 + 25 * np.abs(intraday) + 25 * np.abs(gaps))
    index = pd.bdate_range("2012-01-02", periods=bars, name="date")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=index)


@dataclass(frozen=True)
class FixedSignal(Signal):
    """Test signal that fires on the given bar positions. Also proves new signals plug in without changes."""

    positions: tuple[int, ...] = ()
    side: Direction = Direction.LONG
    name: ClassVar[str] = "fixed"
    family: ClassVar[Family] = Family.PATTERN
    description: ClassVar[str] = "fires on fixed bars"

    @property
    def direction(self) -> Direction:  # type: ignore[override]
        return self.side

    def condition(self, df: pd.DataFrame) -> pd.Series:
        flags = np.zeros(len(df), dtype=bool)
        flags[list(self.positions)] = True
        return pd.Series(flags, index=df.index)


@dataclass(frozen=True)
class RatchetStop(ExitRule):
    """Test exit: a stop that follows the close at `atr_mult` ATRs and only tightens. Proves moving stops work."""

    atr_mult: float = 1.5
    name: ClassVar[str] = "test_ratchet"
    label: ClassVar[str] = "Ratchet stop"
    description: ClassVar[str] = "test only"

    def prepare(self, bars: Bars, direction: Direction) -> TrackerFactory:
        return lambda trade: _Ratchet(bars, direction.sign, self.atr_mult, trade.stop)


class _Ratchet:
    def __init__(self, bars: Bars, sign: float, atr_mult: float, initial: float) -> None:
        self._bars, self._sign, self._atr_mult, self.level = bars, sign, atr_mult, initial

    def orders(self, index: int) -> ExitOrders:
        candidate = self._bars.close[index] - self._sign * self._atr_mult * self._bars.atr[index]
        if self._sign * (candidate - self.level) > 0:
            self.level = float(candidate)
        return ExitOrders(stop=self.level, stop_reason="trailing")


@dataclass(frozen=True)
class AdverseCloseExit(ExitRule):
    """Test exit: leave at the next open after a close against the position. Proves exits at the open work."""

    name: ClassVar[str] = "test_adverse_close"
    label: ClassVar[str] = "Adverse close"
    description: ClassVar[str] = "test only"

    def prepare(self, bars: Bars, direction: Direction) -> TrackerFactory:
        return lambda trade: _AdverseClose(bars.close, direction.sign)


@dataclass(frozen=True)
class _AdverseClose:
    close: np.ndarray
    sign: float

    def orders(self, index: int) -> ExitOrders:
        against = self.sign * (self.close[index] - self.close[index - 1]) < 0
        return ExitOrders(at_open="signal") if against else ExitOrders()


class FakeProvider:
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames
        self.calls: list[tuple[tuple[str, ...], str, str]] = []

    def history(self, tickers: Sequence[str], period: str, interval: str) -> dict[str, pd.DataFrame]:
        self.calls.append((tuple(tickers), period, interval))
        return {ticker: self.frames[ticker] for ticker in tickers if ticker in self.frames}
