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

    def _ranking(self, choice: RuleChoice | None) -> PriorityRule:
        choice = choice or RuleChoice(DEFAULT_RANKING)
        names = [rule.name for rule in self.rankings]
        if choice.name not in names:
            raise ValueError(f"Unknown ranking rule '{choice.name}'. Use: {', '.join(names)}")
        return self._priorities.create(choice.name, choice.params)

    def run(self, request: RotationRequest) -> RotationReport:
        engines = request.engines
        unknown = [name for name in engines if name not in self._engines]
        if unknown or not engines:
            raise ValueError(
                f"Unknown engine(s): {', '.join(unknown) or 'none given'}. Use: {', '.join(self._engines)}"
            )
        settings = self._settings.with_overrides(request.settings)
        ranking = self._ranking(request.ranking)
        weighting_choice = request.weighting or RuleChoice(DEFAULT_WEIGHTING)
        weighting = self._weightings.create(weighting_choice.name, weighting_choice.params)
        safe = request.safe_asset.strip().upper() if request.safe_asset and request.safe_asset.strip() else None
        rotation = build_rotation_config(settings, request.rebalance, safe)
        config = build_backtest_config(settings)
        universe = request.universe
        benchmark = benchmark_ticker(request.benchmark, universe, settings)

        tickers = list(universe.tickers)
        extra = [benchmark, safe] if safe else [benchmark]
        loaded = self._market_data.load(
            [*tickers, *extra], request.period or settings.backtest.period, request.interval
        )
        frames = {ticker: loaded.frames[ticker] for ticker in tickers if ticker in loaded.frames}
        if not frames:
            raise ValueError(f"No data for any ticker of {universe.name}")
        if benchmark not in loaded.frames:
            raise ValueError(f"No data for the benchmark {benchmark}, which buy & hold compares")
        if safe and safe not in loaded.frames:
            raise ValueError(f"No data for the safe asset {safe}")
        safe_frame = loaded.frames[safe] if safe and safe not in frames else None

        built = [self._engines[name]() for name in engines]
        results = [engine.run(frames, config, rotation, ranking, weighting, safe_frame) for engine in built]
        first = results[0]
        if not first.rebalances:
            raise ValueError(
                "No rebalance had a ticker to pick: the history is shorter than the ranking, weighting or absolute "
                "momentum lookback"
            )
        # Every engine picks with the same `targets`, so every run starts at the same rebalance.
        dates = bar_dates(first.equity)
        split = split_history(dates, config.oos_pct)
        close = loaded.frames[benchmark]["close"]
        return RotationReport(
            universe=universe,
            settings=settings,
            config=config,
            rotation=rotation,
            ranking=ranking,
            weighting=weighting,
            benchmark=benchmark,
            benchmark_close=close.astype(float).reindex(first.equity.index, method="ffill"),
            dates=dates,
            split=split,
            targets=first.targets,
            runs=[
                _rotation_run(engine, result, frames, config, rotation, ranking, weighting, safe_frame, close, split)
                for engine, result in zip(built, results, strict=True)
            ],
            missing=[ticker for ticker in loaded.missing if ticker in tickers],
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
