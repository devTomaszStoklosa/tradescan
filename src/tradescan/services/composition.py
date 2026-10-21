"""Composition: the default engines and data provider, and `build_use_cases` wiring every use case."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tradescan.backtest.base import BacktestEngine
from tradescan.backtest.portfolio import PortfolioEngine, VectorizedPortfolioEngine
from tradescan.backtest.rotation import RotationEngine, VectorizedRotationEngine
from tradescan.backtest.trade_rules import RuleCatalog, default_catalog
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.config import Settings
from tradescan.data.cache import CachedProvider
from tradescan.data.provider import DataProvider
from tradescan.data.yfinance_provider import YFinanceProvider
from tradescan.parallel import SequentialRunner, TaskRunner
from tradescan.services.backtest import BacktestUseCase, EngineFactory
from tradescan.services.chart import ChartUseCase
from tradescan.services.edge import EdgeUseCase
from tradescan.services.market import MarketUseCase
from tradescan.services.market_data import MarketData
from tradescan.services.portfolio import PortfolioEngineFactory, PortfolioUseCase
from tradescan.services.rotation import RotationEngineFactory, RotationUseCase
from tradescan.services.rotation_sweep import RotationSweepUseCase
from tradescan.services.scan import ScanUseCase
from tradescan.services.sweep import SweepGridBuilder, SweepUseCase
from tradescan.services.walk_forward import WalkForwardUseCase
from tradescan.services.watchlist_backtest import WatchlistBacktestUseCase
from tradescan.signals.registry import SignalRegistry, default_registry


def _load_cerebro_engine() -> BacktestEngine:
    from tradescan.backtest.cerebro import CerebroEngine

    return CerebroEngine()


def default_engines() -> dict[str, EngineFactory]:
    return {"vectorized": VectorizedEngine, "cerebro": _load_cerebro_engine}


def _load_cerebro_portfolio_engine() -> PortfolioEngine:
    from tradescan.backtest.cerebro_portfolio import CerebroPortfolioEngine

    return CerebroPortfolioEngine()


def default_portfolio_engines() -> dict[str, PortfolioEngineFactory]:
    return {"vectorized": VectorizedPortfolioEngine, "cerebro": _load_cerebro_portfolio_engine}


def _load_cerebro_rotation_engine() -> RotationEngine:
    from tradescan.backtest.cerebro_rotation import CerebroRotationEngine

    return CerebroRotationEngine()


def default_rotation_engines() -> dict[str, RotationEngineFactory]:
    return {"vectorized": VectorizedRotationEngine, "cerebro": _load_cerebro_rotation_engine}


def default_provider(settings: Settings, use_cache: bool = True) -> DataProvider:
    provider = YFinanceProvider()
    if not use_cache:
        return provider
    return CachedProvider(provider, Path(settings.data.cache_dir), settings.data.cache_ttl_hours * 3600.0)


@dataclass(frozen=True)
class UseCases:
    scan: ScanUseCase
    market: MarketUseCase
    edge: EdgeUseCase
    backtest: BacktestUseCase
    sweep: SweepUseCase
    walk_forward: WalkForwardUseCase
    watchlist_backtest: WatchlistBacktestUseCase
    portfolio: PortfolioUseCase
    rotation: RotationUseCase
    rotation_sweep: RotationSweepUseCase
    chart: ChartUseCase


def build_use_cases(
    settings: Settings,
    provider: DataProvider,
    registry: SignalRegistry = default_registry,
    engines: Mapping[str, EngineFactory] | None = None,
    runner: TaskRunner | None = None,
    rules: RuleCatalog = default_catalog,
    portfolio_engines: Mapping[str, PortfolioEngineFactory] | None = None,
    rotation_engines: Mapping[str, RotationEngineFactory] | None = None,
) -> UseCases:
    """`runner` runs per-ticker work and sweeps; pass a `ProcessRunner` to use every core."""
    market_data = MarketData(provider, settings)
    task_runner = runner or SequentialRunner()
    grids = SweepGridBuilder(market_data, settings, registry, rules)
    return UseCases(
        scan=ScanUseCase(market_data, settings, registry, task_runner),
        market=MarketUseCase(market_data, settings, registry),
        edge=EdgeUseCase(market_data, settings, registry, task_runner),
        backtest=BacktestUseCase(market_data, settings, registry, engines or default_engines(), rules),
        sweep=SweepUseCase(grids, task_runner),
        walk_forward=WalkForwardUseCase(grids, task_runner),
        watchlist_backtest=WatchlistBacktestUseCase(market_data, settings, registry, task_runner, rules),
        portfolio=PortfolioUseCase(
            market_data, settings, registry, portfolio_engines or default_portfolio_engines(), rules
        ),
        rotation=RotationUseCase(market_data, settings, rotation_engines or default_rotation_engines()),
        rotation_sweep=RotationSweepUseCase(market_data, settings, task_runner),
        chart=ChartUseCase(market_data, registry),
    )
