"""Backtest: one signal on one ticker with one or more engines."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import pandas as pd

from tradescan.backtest.base import BacktestConfig, BacktestEngine, BacktestResult
from tradescan.backtest.metrics import Metrics, compute_metrics
from tradescan.backtest.monte_carlo import MonteCarlo, closed_r_multiples, simulate
from tradescan.backtest.oos import PeriodMetrics, Split, run_periods, split_history
from tradescan.backtest.trade_rules import RuleCatalog, RuleChoice, TradeRules, default_catalog
from tradescan.config import Settings
from tradescan.data.schema import bar_dates
from tradescan.params import GroupOverrides, Overrides
from tradescan.services.builders import build_backtest_config, build_monte_carlo_config, resolve_settings
from tradescan.services.market_data import LoadedData, MarketData
from tradescan.signals.base import Signal
from tradescan.signals.registry import SignalRegistry

EngineFactory = Callable[[], BacktestEngine]


@dataclass(frozen=True)
class BacktestRequest:
    ticker: str
    signal: str
    engines: tuple[str, ...] = ("vectorized",)
    params: Overrides = field(default_factory=dict)  # the signal's parameters
    settings: GroupOverrides = field(default_factory=dict)
    entry: RuleChoice | None = None  # None: the catalog's default entry
    exits: tuple[RuleChoice, ...] | None = None  # None: the default exits; empty: only the initial stop
    filters: tuple[RuleChoice, ...] = ()  # every one has to allow a signal for it to trade
    benchmark: str | None = None  # compared by the market filter; None: the settings' scan benchmark
    period: str | None = None
    interval: str | None = None


@dataclass(frozen=True)
class EngineRun:
    result: BacktestResult
    metrics: Metrics
    periods: PeriodMetrics | None  # None when the history is too short to split
    monte_carlo: MonteCarlo | None  # of the full history's trades; None with too few closed trades


@dataclass(frozen=True)
class BacktestReport:
    ticker: str
    signal: Signal
    config: BacktestConfig
    rules: TradeRules
    benchmark: str | None  # the benchmark the filters compared; None when no filter reads one
    close: pd.Series
    runs: list[EngineRun]
    split: Split | None


@dataclass(frozen=True)
class ResolvedBacktest:
    """A backtest request turned into validated settings, signal, rules and config."""

    settings: Settings
    signal: Signal
    rules: TradeRules  # without the benchmark's closes, which `load_setup` adds
    config: BacktestConfig
    benchmark: str | None  # the benchmark the filters compare; None when no filter reads one


def resolve_backtest(
    request: BacktestRequest, settings: Settings, registry: SignalRegistry, rules: RuleCatalog
) -> ResolvedBacktest:
    resolved = resolve_settings(settings, request.settings, registry)
    trade_rules = rules.build(request.entry, request.exits, request.filters)
    benchmark = (request.benchmark or resolved.scan.benchmark).upper() if trade_rules.needs_benchmark else None
    return ResolvedBacktest(
        settings=resolved,
        signal=registry.create(request.signal, request.params),
        rules=trade_rules,
        config=build_backtest_config(resolved),
        benchmark=benchmark,
    )


class BacktestUseCase:
    def __init__(
        self,
        market_data: MarketData,
        settings: Settings,
        registry: SignalRegistry,
        engines: Mapping[str, EngineFactory],
        rules: RuleCatalog = default_catalog,
    ) -> None:
        self._market_data = market_data
        self._settings = settings
        self._registry = registry
        self._engines = engines
        self._rules = rules

    @property
    def engine_names(self) -> list[str]:
        return list(self._engines)

    @property
    def rules(self) -> RuleCatalog:
        return self._rules

    def run(self, request: BacktestRequest) -> BacktestReport:
        unknown = [name for name in request.engines if name not in self._engines]
        if unknown or not request.engines:
            raise ValueError(
                f"Unknown engine(s): {', '.join(unknown) or 'none given'}. Use: {', '.join(self._engines)}"
            )
        resolved = resolve_backtest(request, self._settings, self._registry, self._rules)
        signal, config = resolved.signal, resolved.config
        ticker = request.ticker.upper()
        period = request.period or resolved.settings.backtest.period
        df, rules = load_setup(self._market_data, ticker, resolved, period, request.interval)
        split = split_history(bar_dates(df), config.oos_pct)
        monte_carlo = build_monte_carlo_config(resolved.settings)

        runs = []
        for name in request.engines:
            engine = self._engines[name]()
            result = engine.run(ticker, df, signal, config, rules)
            metrics = compute_metrics(result.equity, result.trades, df["close"], config.bars_per_year)
            periods = run_periods(engine, ticker, df, signal, config, rules, split.index) if split else None
            simulations = simulate(closed_r_multiples(result.trades), config.risk_pct, monte_carlo)
            runs.append(EngineRun(result, metrics, periods, simulations))
        return BacktestReport(
            ticker=ticker,
            signal=signal,
            config=config,
            rules=rules,
            benchmark=resolved.benchmark,
            close=df["close"],
            runs=runs,
            split=split,
        )


def load_setup(
    market_data: MarketData, ticker: str, resolved: ResolvedBacktest, period: str, interval: str | None
) -> tuple[pd.DataFrame, TradeRules]:
    """The ticker's bars, and the rules with the benchmark's closes when a filter compares the market."""
    benchmark = resolved.benchmark
    loaded = market_data.load([ticker, benchmark] if benchmark else [ticker], period, interval)
    if ticker not in loaded.frames:
        raise ValueError(f"No data for {ticker}")
    return loaded.frames[ticker], rules_with_benchmark(resolved, loaded)


def rules_with_benchmark(resolved: ResolvedBacktest, loaded: LoadedData) -> TradeRules:
    """The rules with the benchmark's closes when a filter compares the market."""
    benchmark = resolved.benchmark
    if benchmark is None:
        return resolved.rules
    if benchmark not in loaded.frames:
        readers = ", ".join(rule.name for rule in resolved.rules.filters if rule.needs_benchmark)
        raise ValueError(f"No data for the benchmark {benchmark}, which the {readers} filter compares")
    return resolved.rules.with_benchmark(loaded.frames[benchmark]["close"])
