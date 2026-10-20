"""Market regime: the benchmark's trend and the watchlist's breadth."""

from __future__ import annotations

from dataclasses import dataclass, field

from tradescan.config import Settings
from tradescan.params import GroupOverrides
from tradescan.regime import MarketRegime
from tradescan.services.builders import build_regime_analyzer, resolve_settings
from tradescan.services.market_data import MarketData, benchmark_ticker
from tradescan.signals.registry import SignalRegistry
from tradescan.watchlist import Watchlist


@dataclass(frozen=True)
class MarketRequest:
    universe: Watchlist
    settings: GroupOverrides = field(default_factory=dict)
    benchmark: str | None = None
    period: str | None = None
    interval: str | None = None


@dataclass(frozen=True)
class MarketReport:
    universe: Watchlist
    regime: MarketRegime
    missing: list[str]


class MarketUseCase:
    def __init__(self, market_data: MarketData, settings: Settings, registry: SignalRegistry) -> None:
        self._market_data = market_data
        self._settings = settings
        self._registry = registry

    def run(self, request: MarketRequest) -> MarketReport:
        settings = resolve_settings(self._settings, request.settings, self._registry)
        benchmark = benchmark_ticker(request.benchmark, request.universe, settings)
        loaded = self._market_data.load([*request.universe.tickers, benchmark], request.period, request.interval)
        universe_frames = {
            ticker: loaded.frames[ticker] for ticker in request.universe.tickers if ticker in loaded.frames
        }
        return MarketReport(
            universe=request.universe,
            regime=build_regime_analyzer(settings).analyze(benchmark, loaded.frames.get(benchmark), universe_frames),
            missing=[ticker for ticker in loaded.missing if ticker in request.universe.tickers],
        )
