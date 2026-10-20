"""Scan: fresh signals on a watchlist, scored, with a risk plan for each hit."""

from __future__ import annotations

from dataclasses import dataclass, field

from tradescan.config import Settings
from tradescan.parallel import TaskRunner
from tradescan.params import GroupOverrides
from tradescan.regime import MarketRegime
from tradescan.scanner import ScanHit, Scanner, filter_hits
from tradescan.scoring import Scorer
from tradescan.services.builders import (
    build_context_builder,
    build_regime_analyzer,
    build_risk_planner,
    build_scorer,
    resolve_settings,
)
from tradescan.services.market_data import MarketData, SignalFilter, benchmark_ticker
from tradescan.signals.registry import SignalRegistry
from tradescan.watchlist import Watchlist


@dataclass(frozen=True)
class ScanRequest:
    universe: Watchlist
    signals: SignalFilter = field(default_factory=SignalFilter)
    settings: GroupOverrides = field(default_factory=dict)
    signal_params: GroupOverrides = field(default_factory=dict)
    benchmark: str | None = None
    period: str | None = None
    interval: str | None = None


@dataclass(frozen=True)
class ScanReport:
    universe: Watchlist
    regime: MarketRegime
    hits: list[ScanHit]
    missing: list[str]
    skipped: list[str]
    min_score: float
    fresh_bars: int
    edge_horizon: int
    scorer: Scorer  # the one this run used, so reported weights match the scores


class ScanUseCase:
    def __init__(
        self, market_data: MarketData, settings: Settings, registry: SignalRegistry, runner: TaskRunner
    ) -> None:
        self._market_data = market_data
        self._settings = settings
        self._registry = registry
        self._runner = runner

    def run(self, request: ScanRequest) -> ScanReport:
        settings = resolve_settings(self._settings, request.settings, self._registry)
        signals = request.signals.select(self._registry, request.signal_params)
        benchmark = benchmark_ticker(request.benchmark, request.universe, settings)
        loaded = self._market_data.load([*request.universe.tickers, benchmark], request.period, request.interval)
        universe_frames = {
            ticker: loaded.frames[ticker] for ticker in request.universe.tickers if ticker in loaded.frames
        }
        regime = build_regime_analyzer(settings).analyze(benchmark, loaded.frames.get(benchmark), universe_frames)

        scorer = build_scorer(settings)
        scanner = Scanner(
            signals=signals,
            context_builder=build_context_builder(settings),
            scorer=scorer,
            risk_planner=build_risk_planner(settings),
            edge_horizon=settings.scan.edge_horizon,
            fresh_bars=settings.scan.fresh_bars,
            min_bars=settings.scan.min_bars,
            runner=self._runner,
        )
        result = scanner.scan(universe_frames)
        return ScanReport(
            universe=request.universe,
            regime=regime,
            hits=filter_hits(result.hits, min_score=settings.scan.min_score, directions=request.signals.directions()),
            missing=[ticker for ticker in loaded.missing if ticker in request.universe.tickers],
            skipped=result.skipped,
            min_score=settings.scan.min_score,
            fresh_bars=settings.scan.fresh_bars,
            edge_horizon=settings.scan.edge_horizon,
            scorer=scorer,
        )
