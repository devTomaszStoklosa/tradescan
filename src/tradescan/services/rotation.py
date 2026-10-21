"""Momentum rotation: hold the strongest tickers of a watchlist, rebalanced on a calendar, on one or more engines."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import pandas as pd

from tradescan.backtest.base import BacktestConfig
from tradescan.backtest.oos import Split, split_history
from tradescan.backtest.portfolio_metrics import TickerContribution, contributions
from tradescan.backtest.priority import PriorityRule, priority_rules
from tradescan.backtest.rotation import (
    DEFAULT_RANKING,
    Rebalance,
    RotationConfig,
    RotationEngine,
    RotationResult,
    Targets,
    ranking_rules,
    run_rotation_periods,
)
from tradescan.backtest.rotation_metrics import RotationMetrics, rotation_metrics
from tradescan.backtest.rules import RuleRegistry
from tradescan.backtest.trade_rules import RuleChoice
from tradescan.backtest.weighting import DEFAULT_WEIGHTING, WeightRule, weight_rules
from tradescan.config import Settings
from tradescan.data.schema import bar_dates
from tradescan.params import GroupOverrides
from tradescan.services.builders import build_backtest_config, build_rotation_config
from tradescan.services.market_data import MarketData, benchmark_ticker
from tradescan.watchlist import Watchlist

RotationEngineFactory = Callable[[], RotationEngine]


@dataclass(frozen=True)
class RotationRequest:
    """Hold the strongest tickers of `universe`, on each of `engines`. `settings` sets the `[rotation]` holdings and
    absolute momentum, the account, the costs and the out-of-sample share. Without a benchmark of its own, buy & hold
    compares the watchlist's."""

    universe: Watchlist
    ranking: RuleChoice | None = None  # None: the default ranking
    weighting: RuleChoice | None = None  # None: the default weighting
    rebalance: Rebalance = Rebalance.MONTHLY
    safe_asset: str | None = None  # None: cash
    settings: GroupOverrides = field(default_factory=dict)
    benchmark: str | None = None
    period: str | None = None
    interval: str | None = None
    engines: tuple[str, ...] = ("vectorized",)


@dataclass(frozen=True)
class RotationRun:
    result: RotationResult
    full: RotationMetrics
    in_sample: RotationMetrics | None  # None when the run is too short to split
    out_of_sample: RotationMetrics | None
    contributions: list[TickerContribution]  # of the full run, the safe asset last


@dataclass(frozen=True)
class ResolvedRotation:
    """A rotation request with its settings applied and its rules built."""

    settings: Settings
    config: BacktestConfig
    rotation: RotationConfig
    ranking: PriorityRule
    weighting: WeightRule
    benchmark: str  # compared by buy & hold


@dataclass(frozen=True)
class RotationData:
    """The bars a rotation reads, loaded once."""

    frames: dict[str, pd.DataFrame]  # the watchlist's tickers with data, in its order
    safe_frame: pd.DataFrame | None  # the safe asset's when it is not in the watchlist
    benchmark_close: pd.Series  # on the benchmark's own dates
    missing: list[str]  # tickers of the watchlist without data


def resolve_rotation(
    request: RotationRequest,
    settings: Settings,
    priorities: RuleRegistry[PriorityRule],
    weightings: RuleRegistry[WeightRule],
) -> ResolvedRotation:
    """Shared by the rotation and its sweep, which resolves every combination of its swept values."""
    applied = settings.with_overrides(request.settings)
    choice = request.ranking or RuleChoice(DEFAULT_RANKING)
    names = [rule.name for rule in ranking_rules(priorities)]
    if choice.name not in names:
        raise ValueError(f"Unknown ranking rule '{choice.name}'. Use: {', '.join(names)}")
    weighting = request.weighting or RuleChoice(DEFAULT_WEIGHTING)
    safe = request.safe_asset.strip().upper() if request.safe_asset and request.safe_asset.strip() else None
    return ResolvedRotation(
        settings=applied,
        config=build_backtest_config(applied),
        rotation=build_rotation_config(applied, request.rebalance, safe),
        ranking=priorities.create(choice.name, choice.params),
        weighting=weightings.create(weighting.name, weighting.params),
        benchmark=benchmark_ticker(request.benchmark, request.universe, applied),
    )


def load_rotation(market_data: MarketData, request: RotationRequest, resolved: ResolvedRotation) -> RotationData:
    """The watchlist's, the benchmark's and the safe asset's bars; refuses a run without the data it needs."""
    tickers = list(request.universe.tickers)
    benchmark, safe = resolved.benchmark, resolved.rotation.safe_asset
    extra = [benchmark, safe] if safe else [benchmark]
    loaded = market_data.load([*tickers, *extra], request.period or resolved.settings.backtest.period, request.interval)
    frames = {ticker: loaded.frames[ticker] for ticker in tickers if ticker in loaded.frames}
    if not frames:
        raise ValueError(f"No data for any ticker of {request.universe.name}")
    if benchmark not in loaded.frames:
        raise ValueError(f"No data for the benchmark {benchmark}, which buy & hold compares")
    if safe and safe not in loaded.frames:
        raise ValueError(f"No data for the safe asset {safe}")
    return RotationData(
        frames=frames,
        safe_frame=loaded.frames[safe] if safe and safe not in frames else None,
        benchmark_close=loaded.frames[benchmark]["close"],
        missing=[ticker for ticker in loaded.missing if ticker in tickers],
    )


NO_REBALANCE = (
    "No rebalance had a ticker to pick: the history is shorter than the ranking, weighting or absolute "
    "momentum lookback"
)


@dataclass(frozen=True)
class RotationReport:
    universe: Watchlist
    settings: Settings
    config: BacktestConfig
    rotation: RotationConfig
    ranking: PriorityRule
    weighting: WeightRule
    benchmark: str  # compared by buy & hold
    benchmark_close: pd.Series  # on the run's dates, each with the benchmark's last close at or before it
    dates: pd.DatetimeIndex  # the run's dates: every engine starts at the first rebalance with a pick
    split: Split | None  # of the run's dates
    targets: Targets  # what a rebalance at the last close would hold, the same on every engine
    runs: list[RotationRun]  # one per engine, in the request's order
    missing: list[str]


class RotationUseCase:
    def __init__(
        self,
        market_data: MarketData,
        settings: Settings,
        engines: Mapping[str, RotationEngineFactory],
        priorities: RuleRegistry[PriorityRule] = priority_rules,
        weightings: RuleRegistry[WeightRule] = weight_rules,
    ) -> None:
        self._market_data = market_data
        self._settings = settings
        self._engines = engines
        self._priorities = priorities
        self._weightings = weightings

    @property
    def rankings(self) -> list[type[PriorityRule]]:
        return ranking_rules(self._priorities)

    @property
    def weightings(self) -> RuleRegistry[WeightRule]:
        return self._weightings

    def run(self, request: RotationRequest) -> RotationReport:
        engines = request.engines
        unknown = [name for name in engines if name not in self._engines]
        if unknown or not engines:
            raise ValueError(
                f"Unknown engine(s): {', '.join(unknown) or 'none given'}. Use: {', '.join(self._engines)}"
            )
        resolved = resolve_rotation(request, self._settings, self._priorities, self._weightings)
        data = load_rotation(self._market_data, request, resolved)
        frames, safe_frame = data.frames, data.safe_frame
        config, rotation, ranking, weighting = resolved.config, resolved.rotation, resolved.ranking, resolved.weighting

        built = [self._engines[name]() for name in engines]
        results = [engine.run(frames, config, rotation, ranking, weighting, safe_frame) for engine in built]
        first = results[0]
        if not first.rebalances:
            raise ValueError(NO_REBALANCE)
        # Every engine picks with the same `targets`, so every run starts at the same rebalance.
        dates = bar_dates(first.equity)
        split = split_history(dates, config.oos_pct)
        close = data.benchmark_close
        return RotationReport(
            universe=request.universe,
            settings=resolved.settings,
            config=config,
            rotation=rotation,
            ranking=ranking,
            weighting=weighting,
            benchmark=resolved.benchmark,
            benchmark_close=close.astype(float).reindex(first.equity.index, method="ffill"),
            dates=dates,
            split=split,
            targets=first.targets,
            runs=[
                _rotation_run(engine, result, frames, config, rotation, ranking, weighting, safe_frame, close, split)
                for engine, result in zip(built, results, strict=True)
            ],
            missing=data.missing,
        )


def _rotation_run(
    engine: RotationEngine,
    result: RotationResult,
    frames: Mapping[str, pd.DataFrame],
    config: BacktestConfig,
    rotation: RotationConfig,
    ranking: PriorityRule,
    weighting: WeightRule,
    safe_frame: pd.DataFrame | None,
    close: pd.Series,
    split: Split | None,
) -> RotationRun:
    """The metrics of one engine's full run `result` and, with a split, of both its periods."""
    bars_per_year = config.bars_per_year
    full = rotation_metrics(result, close, bars_per_year)
    shares = contributions(result, config.initial_equity)
    if split is None:
        return RotationRun(result, full, None, None, shares)
    periods = run_rotation_periods(
        engine, frames, config, rotation, ranking, weighting, safe_frame, split.out_of_sample[0]
    )
    return RotationRun(
        result=result,
        full=full,
        in_sample=rotation_metrics(periods.in_sample, close, bars_per_year),
        out_of_sample=rotation_metrics(periods.out_of_sample, close, bars_per_year),
        contributions=shares,
    )
