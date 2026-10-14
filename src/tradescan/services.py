"""Use cases shared by the CLI and the HTTP API.

Each use case takes a request dataclass and returns a report dataclass; neither knows about
argparse, HTTP or rendering. `build_use_cases` wires them from settings and a data provider.

Requests carry per-run overrides: `settings` ({section: {parameter: value}}) and signal parameters
({signal name: {parameter: value}}). Both are validated against the declared ranges, and the
configured settings are never modified.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from tradescan.backtest.base import BacktestConfig, BacktestEngine, BacktestResult
from tradescan.backtest.edge import EdgeSampler, EdgeStats, combine_samples
from tradescan.backtest.metrics import Metrics, compute_metrics
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.config import Settings
from tradescan.context import ContextBuilder
from tradescan.data.cache import CachedProvider
from tradescan.data.provider import DataProvider
from tradescan.data.yfinance_provider import YFinanceProvider
from tradescan.indicators import sma
from tradescan.parallel import SequentialRunner, TaskRunner
from tradescan.params import GroupOverrides, Overrides, check_group
from tradescan.regime import MarketRegime, MarketRegimeAnalyzer
from tradescan.risk import RiskPlanner
from tradescan.scanner import ScanHit, Scanner, filter_hits
from tradescan.scoring import Scorer
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.registry import SignalRegistry, default_registry
from tradescan.watchlist import Watchlist

EngineFactory = Callable[[], BacktestEngine]


def _load_cerebro_engine() -> BacktestEngine:
    from tradescan.backtest.cerebro import CerebroEngine

    return CerebroEngine()


def default_engines() -> dict[str, EngineFactory]:
    return {"vectorized": VectorizedEngine, "cerebro": _load_cerebro_engine}


def default_provider(settings: Settings, use_cache: bool = True) -> DataProvider:
    provider = YFinanceProvider()
    if not use_cache:
        return provider
    return CachedProvider(provider, Path(settings.data.cache_dir), settings.data.cache_ttl_hours * 3600.0)


# ---------------------------------------------------------------------------
# Builders: settings -> collaborators


def build_scorer(settings: Settings) -> Scorer:
    scoring = settings.scoring
    return Scorer(
        family_weights=scoring.family_weights,
        signal_weights=scoring.signal_weights,
        trend_bonus=scoring.trend_bonus,
        weekly_bonus=scoring.weekly_bonus,
        rs_bonus=scoring.rs_bonus,
        rs_strong_pct=scoring.rs_strong_pct,
    )


def build_context_builder(settings: Settings) -> ContextBuilder:
    trend = settings.trend
    return ContextBuilder(
        atr_period=settings.risk.atr_period,
        fast_period=trend.fast_period,
        slow_period=trend.slow_period,
        weekly_period=trend.weekly_period,
        rs_periods=trend.rs_periods,
        rs_weights=trend.rs_weights,
    )


def build_regime_analyzer(settings: Settings) -> MarketRegimeAnalyzer:
    regime = settings.regime
    return MarketRegimeAnalyzer(
        fast_period=regime.fast_period,
        slow_period=regime.slow_period,
        high_low_period=regime.high_low_period,
        risk_on_breadth=regime.risk_on_breadth,
        risk_off_breadth=regime.risk_off_breadth,
    )


def build_risk_planner(settings: Settings) -> RiskPlanner:
    account, risk = settings.account, settings.risk
    return RiskPlanner(
        equity=account.equity,
        risk_pct=account.risk_pct,
        max_position_pct=account.max_position_pct,
        atr_mult=risk.atr_mult,
        targets_r=risk.targets_r,
        lot_size=account.lot_size,
    )


def build_backtest_config(settings: Settings) -> BacktestConfig:
    account, backtest, risk = settings.account, settings.backtest, settings.risk
    return BacktestConfig(
        initial_equity=account.equity,
        risk_pct=account.risk_pct,
        max_position_pct=account.max_position_pct,
        lot_size=account.lot_size,
        atr_period=risk.atr_period,
        atr_mult=risk.atr_mult,
        target_r=backtest.target_r,
        max_hold_bars=backtest.max_hold_bars,
        commission_pct=backtest.commission_pct,
        slippage_pct=backtest.slippage_pct,
        bars_per_year=backtest.bars_per_year,
    )


def resolve_settings(settings: Settings, overrides: GroupOverrides, registry: SignalRegistry) -> Settings:
    """The configured settings plus one run's overrides; per-signal weights must name known signals."""
    weights = (overrides.get("scoring") or {}).get("signal_weights") or {}
    if isinstance(weights, Mapping):
        check_group(weights, registry.names(), "signal weight(s)")
    return settings.with_overrides(overrides)


# ---------------------------------------------------------------------------
# Requests shared by several use cases


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


def _benchmark(requested: str | None, universe: Watchlist, settings: Settings) -> str:
    return (requested or universe.benchmark or settings.scan.benchmark).upper()


# ---------------------------------------------------------------------------
# Scan


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
    def __init__(self, market_data: MarketData, settings: Settings, registry: SignalRegistry, runner: TaskRunner) -> None:
        self._market_data = market_data
        self._settings = settings
        self._registry = registry
        self._runner = runner

    def run(self, request: ScanRequest) -> ScanReport:
        settings = resolve_settings(self._settings, request.settings, self._registry)
        signals = request.signals.select(self._registry, request.signal_params)
        benchmark = _benchmark(request.benchmark, request.universe, settings)
        loaded = self._market_data.load([*request.universe.tickers, benchmark], request.period, request.interval)
        universe_frames = {ticker: loaded.frames[ticker] for ticker in request.universe.tickers if ticker in loaded.frames}
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


# ---------------------------------------------------------------------------
# Market regime


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
        benchmark = _benchmark(request.benchmark, request.universe, settings)
        loaded = self._market_data.load([*request.universe.tickers, benchmark], request.period, request.interval)
        universe_frames = {ticker: loaded.frames[ticker] for ticker in request.universe.tickers if ticker in loaded.frames}
        return MarketReport(
            universe=request.universe,
            regime=build_regime_analyzer(settings).analyze(benchmark, loaded.frames.get(benchmark), universe_frames),
            missing=[ticker for ticker in loaded.missing if ticker in request.universe.tickers],
        )


# ---------------------------------------------------------------------------
# Edge


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
    def __init__(self, market_data: MarketData, settings: Settings, registry: SignalRegistry, runner: TaskRunner) -> None:
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


# ---------------------------------------------------------------------------
# Backtest


@dataclass(frozen=True)
class BacktestRequest:
    ticker: str
    signal: str
    engines: tuple[str, ...] = ("vectorized",)
    params: Overrides = field(default_factory=dict)  # the signal's parameters
    settings: GroupOverrides = field(default_factory=dict)
    period: str | None = None
    interval: str | None = None


@dataclass(frozen=True)
class EngineRun:
    result: BacktestResult
    metrics: Metrics


@dataclass(frozen=True)
class BacktestReport:
    ticker: str
    signal: Signal
    config: BacktestConfig
    close: pd.Series
    runs: list[EngineRun]


class BacktestUseCase:
    def __init__(
        self,
        market_data: MarketData,
        settings: Settings,
        registry: SignalRegistry,
        engines: Mapping[str, EngineFactory],
    ) -> None:
        self._market_data = market_data
        self._settings = settings
        self._registry = registry
        self._engines = engines

    @property
    def engine_names(self) -> list[str]:
        return list(self._engines)

    def run(self, request: BacktestRequest) -> BacktestReport:
        unknown = [name for name in request.engines if name not in self._engines]
        if unknown or not request.engines:
            raise ValueError(f"Unknown engine(s): {', '.join(unknown) or 'none given'}. Use: {', '.join(self._engines)}")
        settings = resolve_settings(self._settings, request.settings, self._registry)
        signal = self._registry.create(request.signal, request.params)
        ticker = request.ticker.upper()
        loaded = self._market_data.load([ticker], request.period or settings.backtest.period, request.interval)
        if ticker not in loaded.frames:
            raise ValueError(f"No data for {ticker}")
        df = loaded.frames[ticker]

        config = build_backtest_config(settings)
        runs = []
        for name in request.engines:
            result = self._engines[name]().run(ticker, df, signal, config)
            runs.append(EngineRun(result, compute_metrics(result.equity, result.trades, df["close"], config.bars_per_year)))
        return BacktestReport(ticker=ticker, signal=signal, config=config, close=df["close"], runs=runs)


# ---------------------------------------------------------------------------
# Chart


@dataclass(frozen=True)
class ChartRequest:
    ticker: str
    signals: tuple[str, ...] = ()
    signal_params: GroupOverrides = field(default_factory=dict)
    period: str | None = None
    interval: str | None = None


@dataclass(frozen=True)
class SignalEvent:
    date: pd.Timestamp
    signal: str
    direction: Direction


@dataclass(frozen=True)
class ChartData:
    ticker: str
    bars: pd.DataFrame
    sma_fast: pd.Series
    sma_slow: pd.Series
    events: list[SignalEvent]


class ChartUseCase:
    def __init__(
        self,
        market_data: MarketData,
        registry: SignalRegistry,
        fast_period: int = 50,
        slow_period: int = 200,
    ) -> None:
        self._market_data = market_data
        self._registry = registry
        self._fast_period = fast_period
        self._slow_period = slow_period

    def run(self, request: ChartRequest) -> ChartData:
        ticker = request.ticker.upper()
        self._registry.check_params(request.signal_params)
        signals = [self._registry.create(name, request.signal_params.get(name)) for name in request.signals]
        loaded = self._market_data.load([ticker], request.period, request.interval)
        if ticker not in loaded.frames:
            raise ValueError(f"No data for {ticker}")
        df = loaded.frames[ticker]
        events = [
            SignalEvent(date=date, signal=signal.name, direction=signal.direction)
            for signal in signals
            for date in df.index[signal.events(df).to_numpy()]
        ]
        events.sort(key=lambda event: event.date)
        return ChartData(
            ticker=ticker,
            bars=df,
            sma_fast=sma(df["close"], self._fast_period),
            sma_slow=sma(df["close"], self._slow_period),
            events=events,
        )


# ---------------------------------------------------------------------------
# Composition


@dataclass(frozen=True)
class UseCases:
    scan: ScanUseCase
    market: MarketUseCase
    edge: EdgeUseCase
    backtest: BacktestUseCase
    chart: ChartUseCase


def build_use_cases(
    settings: Settings,
    provider: DataProvider,
    registry: SignalRegistry = default_registry,
    engines: Mapping[str, EngineFactory] | None = None,
    runner: TaskRunner | None = None,
) -> UseCases:
    """`runner` runs per-ticker work; pass a `ProcessRunner` to use every core on large universes."""
    market_data = MarketData(provider, settings)
    task_runner = runner or SequentialRunner()
    return UseCases(
        scan=ScanUseCase(market_data, settings, registry, task_runner),
        market=MarketUseCase(market_data, settings, registry),
        edge=EdgeUseCase(market_data, settings, registry, task_runner),
        backtest=BacktestUseCase(market_data, settings, registry, engines or default_engines()),
        chart=ChartUseCase(market_data, registry),
    )
