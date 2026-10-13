"""Use cases shared by the CLI and the HTTP API.

Each use case takes a request dataclass and returns a report dataclass; neither knows about
argparse, HTTP or rendering. `build_use_cases` wires them from settings and a data provider.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from tradescan.backtest.base import BacktestConfig, BacktestEngine, BacktestResult
from tradescan.backtest.edge import EdgeAnalyzer, EdgeStats
from tradescan.backtest.metrics import Metrics, compute_metrics
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.config import Settings
from tradescan.context import ContextBuilder
from tradescan.data.cache import CachedProvider
from tradescan.data.provider import DataProvider
from tradescan.data.yfinance_provider import YFinanceProvider
from tradescan.indicators import sma
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


# ---------------------------------------------------------------------------
# Requests shared by several use cases


@dataclass(frozen=True)
class SignalFilter:
    names: tuple[str, ...] = ()
    families: tuple[Family, ...] = ()
    direction: Direction | None = None  # None means both directions

    def directions(self) -> set[Direction] | None:
        return None if self.direction is None else {self.direction}

    def select(self, registry: SignalRegistry) -> list[Signal]:
        return registry.select(names=self.names or None, families=set(self.families) or None, directions=self.directions())


@dataclass(frozen=True)
class AccountOverrides:
    equity: float | None = None
    risk_pct: float | None = None
    lot_size: float | None = None


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
    account: AccountOverrides = field(default_factory=AccountOverrides)
    fresh_bars: int | None = None
    min_score: float | None = None
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


class ScanUseCase:
    def __init__(self, market_data: MarketData, settings: Settings, registry: SignalRegistry) -> None:
        self._market_data = market_data
        self._settings = settings
        self._registry = registry

    def run(self, request: ScanRequest) -> ScanReport:
        settings = self._settings
        benchmark = _benchmark(request.benchmark, request.universe, settings)
        loaded = self._market_data.load([*request.universe.tickers, benchmark], request.period, request.interval)
        universe_frames = {ticker: loaded.frames[ticker] for ticker in request.universe.tickers if ticker in loaded.frames}
        regime = MarketRegimeAnalyzer().analyze(benchmark, loaded.frames.get(benchmark), universe_frames)

        fresh_bars = request.fresh_bars or settings.scan.fresh_bars
        scanner = Scanner(
            signals=request.signals.select(self._registry),
            context_builder=ContextBuilder(atr_period=settings.risk.atr_period),
            scorer=build_scorer(settings),
            risk_planner=self._risk_planner(request.account),
            edge_analyzer=EdgeAnalyzer(settings.scan.edge_horizon),
            fresh_bars=fresh_bars,
            min_bars=settings.scan.min_bars,
        )
        result = scanner.scan(universe_frames)
        min_score = settings.scan.min_score if request.min_score is None else request.min_score
        return ScanReport(
            universe=request.universe,
            regime=regime,
            hits=filter_hits(result.hits, min_score=min_score, directions=request.signals.directions()),
            missing=[ticker for ticker in loaded.missing if ticker in request.universe.tickers],
            skipped=result.skipped,
            min_score=min_score,
            fresh_bars=fresh_bars,
            edge_horizon=settings.scan.edge_horizon,
        )

    def _risk_planner(self, account: AccountOverrides) -> RiskPlanner:
        defaults = self._settings.account
        return RiskPlanner(
            equity=account.equity or defaults.equity,
            risk_pct=account.risk_pct or defaults.risk_pct,
            max_position_pct=defaults.max_position_pct,
            atr_mult=self._settings.risk.atr_mult,
            targets_r=self._settings.risk.targets_r,
            lot_size=account.lot_size or defaults.lot_size,
        )


# ---------------------------------------------------------------------------
# Market regime


@dataclass(frozen=True)
class MarketRequest:
    universe: Watchlist
    benchmark: str | None = None
    period: str | None = None
    interval: str | None = None


@dataclass(frozen=True)
class MarketReport:
    universe: Watchlist
    regime: MarketRegime
    missing: list[str]


class MarketUseCase:
    def __init__(self, market_data: MarketData, settings: Settings) -> None:
        self._market_data = market_data
        self._settings = settings

    def run(self, request: MarketRequest) -> MarketReport:
        benchmark = _benchmark(request.benchmark, request.universe, self._settings)
        loaded = self._market_data.load([*request.universe.tickers, benchmark], request.period, request.interval)
        universe_frames = {ticker: loaded.frames[ticker] for ticker in request.universe.tickers if ticker in loaded.frames}
        return MarketReport(
            universe=request.universe,
            regime=MarketRegimeAnalyzer().analyze(benchmark, loaded.frames.get(benchmark), universe_frames),
            missing=[ticker for ticker in loaded.missing if ticker in request.universe.tickers],
        )


# ---------------------------------------------------------------------------
# Edge


@dataclass(frozen=True)
class EdgeRequest:
    universe: Watchlist
    signals: SignalFilter = field(default_factory=SignalFilter)
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
    def __init__(self, market_data: MarketData, settings: Settings, registry: SignalRegistry) -> None:
        self._market_data = market_data
        self._settings = settings
        self._registry = registry

    def run(self, request: EdgeRequest) -> EdgeReport:
        if not request.horizons or min(request.horizons) < 1:
            raise ValueError("horizons must be positive integers, e.g. 5,10,20")
        period = request.period or self._settings.backtest.period
        loaded = self._market_data.load(request.universe.tickers, period, request.interval)
        histories = list(loaded.frames.values())
        analyzers = [EdgeAnalyzer(horizon) for horizon in request.horizons]
        rows = [
            EdgeRow(signal=signal, stats=tuple(analyzer.analyze(histories, signal) for analyzer in analyzers))
            for signal in request.signals.select(self._registry)
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
    account: AccountOverrides = field(default_factory=AccountOverrides)
    atr_mult: float | None = None
    target_r: float | None = None
    max_hold_bars: int | None = None
    commission_pct: float | None = None
    slippage_pct: float | None = None
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
        ticker = request.ticker.upper()
        signal = self._registry.create(request.signal)
        loaded = self._market_data.load([ticker], request.period or self._settings.backtest.period, request.interval)
        if ticker not in loaded.frames:
            raise ValueError(f"No data for {ticker}")
        df = loaded.frames[ticker]

        config = self._config(request)
        runs = []
        for name in request.engines:
            result = self._engines[name]().run(ticker, df, signal, config)
            runs.append(EngineRun(result, compute_metrics(result.equity, result.trades, df["close"], config.bars_per_year)))
        return BacktestReport(ticker=ticker, signal=signal, config=config, close=df["close"], runs=runs)

    def _config(self, request: BacktestRequest) -> BacktestConfig:
        account, backtest, risk = self._settings.account, self._settings.backtest, self._settings.risk
        overrides = request.account
        return BacktestConfig(
            initial_equity=overrides.equity or account.equity,
            risk_pct=overrides.risk_pct or account.risk_pct,
            max_position_pct=account.max_position_pct,
            lot_size=overrides.lot_size or account.lot_size,
            atr_period=risk.atr_period,
            atr_mult=request.atr_mult or risk.atr_mult,
            target_r=request.target_r or backtest.target_r,
            max_hold_bars=request.max_hold_bars or backtest.max_hold_bars,
            commission_pct=backtest.commission_pct if request.commission_pct is None else request.commission_pct,
            slippage_pct=backtest.slippage_pct if request.slippage_pct is None else request.slippage_pct,
            bars_per_year=backtest.bars_per_year,
        )


# ---------------------------------------------------------------------------
# Chart


@dataclass(frozen=True)
class ChartRequest:
    ticker: str
    signals: tuple[str, ...] = ()
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
        signals = [self._registry.create(name) for name in request.signals]
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
) -> UseCases:
    market_data = MarketData(provider, settings)
    return UseCases(
        scan=ScanUseCase(market_data, settings, registry),
        market=MarketUseCase(market_data, settings),
        edge=EdgeUseCase(market_data, settings, registry),
        backtest=BacktestUseCase(market_data, settings, registry, engines or default_engines()),
        chart=ChartUseCase(market_data, registry),
    )
