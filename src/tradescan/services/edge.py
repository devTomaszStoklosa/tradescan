"""Edge: historical forward returns after each signal."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from tradescan.backtest.edge import EdgeSampler, EdgeStats, combine_samples
from tradescan.config import Settings
from tradescan.parallel import TaskRunner
from tradescan.params import GroupOverrides
from tradescan.services.market_data import MarketData, SignalFilter
from tradescan.signals.base import Signal
from tradescan.signals.registry import SignalRegistry
from tradescan.watchlist import Watchlist


@dataclass(frozen=True)
class EdgeRequest:
    universe: Watchlist
    signals: SignalFilter = field(default_factory=SignalFilter)
    signal_params: GroupOverrides = field(default_factory=dict)
    horizons: tuple[int, ...] = (5, 10, 20)
    min_events: int = 0
    period: str | None = None
    interval: str | None = None


@dataclass(frozen=True)
class EdgeRow:
    signal: Signal
    stats: tuple[EdgeStats, ...]


@dataclass(frozen=True)
class EdgeReport:
    universe: Watchlist
    horizons: tuple[int, ...]
    rows: list[EdgeRow]
    tickers: int
    missing: list[str]


class EdgeUseCase:
    def __init__(
        self, market_data: MarketData, settings: Settings, registry: SignalRegistry, runner: TaskRunner
    ) -> None:
        self._market_data = market_data
        self._settings = settings
        self._registry = registry
        self._runner = runner

    def run(self, request: EdgeRequest) -> EdgeReport:
        if not request.horizons or min(request.horizons) < 1:
            raise ValueError("horizons must be positive integers, e.g. 5,10,20")
        signals = tuple(request.signals.select(self._registry, request.signal_params))
        period = request.period or self._settings.backtest.period
        loaded = self._market_data.load(request.universe.tickers, period, request.interval)
        horizons = tuple(request.horizons)
        # per_ticker[t][s][h]: samples of signal s at horizon h on ticker t, one job per ticker.
        per_ticker = self._runner.map(EdgeSampler(signals, horizons), list(loaded.frames.values()))
        rows = [
            EdgeRow(
                signal=signal,
                stats=tuple(
                    combine_samples(signal.name, horizon, [samples[s][h] for samples in per_ticker])
                    for h, horizon in enumerate(horizons)
                ),
            )
            for s, signal in enumerate(signals)
        ]
        rows = [row for row in rows if row.stats[0].events >= request.min_events]
        middle = len(request.horizons) // 2
        rows.sort(key=lambda row: _descending_nan_last(row.stats[middle].edge))
        return EdgeReport(
            universe=request.universe,
            horizons=tuple(request.horizons),
            rows=rows,
            tickers=len(loaded.frames),
            missing=loaded.missing,
        )


def _descending_nan_last(value: float) -> tuple[bool, float]:
    return (math.isnan(value), -value if not math.isnan(value) else 0.0)
