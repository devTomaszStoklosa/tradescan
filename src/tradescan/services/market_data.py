"""Loading market data, and the signal filter several use cases share."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from tradescan.config import Settings
from tradescan.data.provider import DataProvider
from tradescan.params import GroupOverrides
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.registry import SignalRegistry
from tradescan.watchlist import Watchlist


@dataclass(frozen=True)
class SignalFilter:
    names: tuple[str, ...] = ()
    families: tuple[Family, ...] = ()
    direction: Direction | None = None  # None means both directions

    def directions(self) -> set[Direction] | None:
        return None if self.direction is None else {self.direction}

    def select(self, registry: SignalRegistry, params: GroupOverrides | None = None) -> list[Signal]:
        return registry.select(
            names=self.names or None, families=set(self.families) or None, directions=self.directions(), params=params
        )


@dataclass(frozen=True)
class LoadedData:
    frames: dict[str, pd.DataFrame]
    missing: list[str]


class MarketData:
    """Loads frames with the configured defaults and reports which tickers returned nothing."""

    def __init__(self, provider: DataProvider, settings: Settings) -> None:
        self._provider = provider
        self._settings = settings

    def load(self, tickers: Sequence[str], period: str | None = None, interval: str | None = None) -> LoadedData:
        unique = list(dict.fromkeys(tickers))
        frames = self._provider.history(
            unique, period or self._settings.data.period, interval or self._settings.data.interval
        )
        return LoadedData(frames=frames, missing=[ticker for ticker in unique if ticker not in frames])


def benchmark_ticker(requested: str | None, universe: Watchlist, settings: Settings) -> str:
    return (requested or universe.benchmark or settings.scan.benchmark).upper()
