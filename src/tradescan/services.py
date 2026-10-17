"""Use cases shared by the CLI and the HTTP API.

Each use case takes a request dataclass and returns a report dataclass; neither knows about
argparse, HTTP or rendering. `build_use_cases` wires them from settings and a data provider.

Requests carry per-run overrides: `settings` ({section: {parameter: value}}) and signal parameters
({signal name: {parameter: value}}); a backtest also names its entry filters, entry rule and exit rules
with their parameters. All are validated against the declared ranges, and the configured settings are never modified.
A sweep reruns one backtest setup over a grid of one or two of those parameters, a watchlist backtest
runs it on every ticker of a watchlist, and a portfolio backtest on every ticker of a watchlist with one
shared equity.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

import pandas as pd

from tradescan.backtest.base import BacktestConfig, BacktestEngine, BacktestResult
from tradescan.backtest.edge import EdgeSampler, EdgeStats, combine_samples
from tradescan.backtest.metrics import Metrics, compute_metrics
from tradescan.backtest.monte_carlo import MonteCarlo, MonteCarloConfig, closed_r_multiples, simulate
from tradescan.backtest.oos import MIN_PERIOD_BARS, PeriodMetrics, Split, run_periods, split_history
from tradescan.backtest.allocation import PortfolioConfig
from tradescan.backtest.pooled import BREAK_EVEN, PooledTrades, Spread, pool_trades, spread
from tradescan.backtest.portfolio import (
    PortfolioEngine,
    PortfolioResult,
    VectorizedPortfolioEngine,
    run_portfolio_periods,
    shared_calendar,
)
from tradescan.backtest.portfolio_metrics import PortfolioMetrics, TickerContribution, contributions, portfolio_metrics
from tradescan.backtest.priority import DEFAULT_PRIORITY, PriorityRule, ScanScore, priority_rules
from tradescan.backtest.rules import Rule, RuleRegistry
from tradescan.backtest.sweep import SweepAxis, SweepCase, SweepJob, SweepTarget, check_axes, grid
from tradescan.backtest.tickers import Period, PeriodRun, TickerJob, TickerRun
from tradescan.backtest.trade_rules import RuleCatalog, RuleChoice, TradeRules, default_catalog
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.config import Settings
from tradescan.context import ContextBuilder
from tradescan.data.cache import CachedProvider
from tradescan.data.provider import DataProvider
from tradescan.data.yfinance_provider import YFinanceProvider
from tradescan.indicators import sma
from tradescan.parallel import SequentialRunner, TaskRunner
from tradescan.params import GroupOverrides, Overrides, ParamSpec, check_group, check_values, parameters_of
from tradescan.regime import MarketRegime, MarketRegimeAnalyzer
from tradescan.risk import RiskPlanner
from tradescan.scanner import ScanHit, Scanner, filter_hits
from tradescan.scoring import Scorer
from tradescan.signals.base import Direction, Family, Signal
from tradescan.signals.registry import SignalRegistry, default_registry
from tradescan.watchlist import Watchlist

EngineFactory = Callable[[], BacktestEngine]
PortfolioEngineFactory = Callable[[], PortfolioEngine]


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
        commission_pct=backtest.commission_pct,
        slippage_pct=backtest.slippage_pct,
        bars_per_year=backtest.bars_per_year,
        oos_pct=backtest.oos_pct,
    )


def build_monte_carlo_config(settings: Settings) -> MonteCarloConfig:
    monte_carlo = settings.monte_carlo
    return MonteCarloConfig(
        simulations=monte_carlo.simulations, ruin_drawdown_pct=monte_carlo.ruin_drawdown_pct, seed=monte_carlo.seed
    )


def build_portfolio_config(settings: Settings) -> PortfolioConfig:
    portfolio = settings.portfolio
    return PortfolioConfig(max_positions=portfolio.max_positions, max_exposure_pct=portfolio.max_exposure_pct)


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
    rules: TradeRules  # without the benchmark's closes, which `_load_setup` adds
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
            raise ValueError(f"Unknown engine(s): {', '.join(unknown) or 'none given'}. Use: {', '.join(self._engines)}")
        resolved = resolve_backtest(request, self._settings, self._registry, self._rules)
        signal, config = resolved.signal, resolved.config
        ticker = request.ticker.upper()
        period = request.period or resolved.settings.backtest.period
        df, rules = _load_setup(self._market_data, ticker, resolved, period, request.interval)
        split = split_history(df.index, config.oos_pct)
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


def _load_setup(
    market_data: MarketData, ticker: str, resolved: ResolvedBacktest, period: str, interval: str | None
) -> tuple[pd.DataFrame, TradeRules]:
    """The ticker's bars, and the rules with the benchmark's closes when a filter compares the market."""
    benchmark = resolved.benchmark
    loaded = market_data.load([ticker, benchmark] if benchmark else [ticker], period, interval)
    if ticker not in loaded.frames:
        raise ValueError(f"No data for {ticker}")
    return loaded.frames[ticker], _with_benchmark(resolved, loaded)


def _with_benchmark(resolved: ResolvedBacktest, loaded: LoadedData) -> TradeRules:
    """The rules with the benchmark's closes when a filter compares the market."""
    benchmark = resolved.benchmark
    if benchmark is None:
        return resolved.rules
    if benchmark not in loaded.frames:
        readers = ", ".join(rule.name for rule in resolved.rules.filters if rule.needs_benchmark)
        raise ValueError(f"No data for the benchmark {benchmark}, which the {readers} filter compares")
    return resolved.rules.with_benchmark(loaded.frames[benchmark]["close"])


# ---------------------------------------------------------------------------
# Sweep


@dataclass(frozen=True)
class SweepRequest:
    """`setup` is the backtest every combination starts from. Its `engines` are ignored: sweeps run on the
    vectorized engine, which gives the same trades as Cerebro many times faster."""

    setup: BacktestRequest
    axes: tuple[SweepAxis, ...]


@dataclass(frozen=True)
class SweptParameter:
    axis: SweepAxis  # with validated values
    spec: ParamSpec  # the declaration; its default is the setup's own value


@dataclass(frozen=True)
class SweepCell:
    values: tuple[float, ...]  # one per axis
    periods: PeriodMetrics | None
    error: str | None = None  # why this combination could not run, e.g. a cross-field rule


@dataclass(frozen=True)
class SweepReport:
    ticker: str
    base: ResolvedBacktest
    parameters: tuple[SweptParameter, ...]
    close: pd.Series
    split: Split
    cells: list[SweepCell]


# Settings sections a backtest reads. The out-of-sample share defines the split itself, so it is fixed.
SWEEP_SECTIONS = ("account", "risk", "backtest")
NOT_SWEEPABLE = {("backtest", "oos_pct")}


class SweepUseCase:
    def __init__(
        self,
        market_data: MarketData,
        settings: Settings,
        registry: SignalRegistry,
        runner: TaskRunner,
        rules: RuleCatalog = default_catalog,
    ) -> None:
        self._market_data = market_data
        self._settings = settings
        self._registry = registry
        self._runner = runner
        self._rules = rules

    def run(self, request: SweepRequest) -> SweepReport:
        check_axes(request.axes)
        setup = self._named_rules(request.setup)
        base = resolve_backtest(setup, self._settings, self._registry, self._rules)
        parameters = tuple(self._check(axis, base) for axis in request.axes)
        axes = tuple(parameter.axis for parameter in parameters)

        ticker = setup.ticker.upper()
        period = setup.period or base.settings.backtest.period
        df, base_rules = _load_setup(self._market_data, ticker, base, period, setup.interval)
        split = split_history(df.index, base.config.oos_pct)
        if split is None:
            raise ValueError(
                f"{ticker} has {len(df)} bars: too few to split at {base.config.oos_pct:g}% "
                f"with at least {MIN_PERIOD_BARS} bars in each period. Use a longer history."
            )

        cells: list[SweepCell] = []
        cases: list[tuple[int, SweepCase]] = []
        for values in grid(axes):
            combination = setup
            for axis, value in zip(axes, values):
                combination = _APPLY[axis.target](combination, axis, value)
            try:
                resolved = resolve_backtest(combination, self._settings, self._registry, self._rules)
            except ValueError as error:
                cells.append(SweepCell(values, None, str(error)))
                continue
            rules = resolved.rules.with_benchmark(base_rules.benchmark_close)  # no axis changes the benchmark
            cases.append((len(cells), SweepCase(resolved.signal, rules, resolved.config)))
            cells.append(SweepCell(values, None))
        results = self._runner.map(SweepJob(ticker, df, split.index), [case for _, case in cases])
        for (position, _), periods in zip(cases, results):
            cells[position] = replace(cells[position], periods=periods)
        return SweepReport(ticker=ticker, base=base, parameters=parameters, close=df["close"], split=split, cells=cells)

    def _named_rules(self, setup: BacktestRequest) -> BacktestRequest:
        """The setup with its entry and exits named, so axes can refer to the default rules too."""
        exits = setup.exits if setup.exits is not None else tuple(RuleChoice(name) for name in self._rules.default_exits)
        return replace(setup, entry=setup.entry or RuleChoice(self._rules.default_entry), exits=exits)

    def _check(self, axis: SweepAxis, base: ResolvedBacktest) -> SweptParameter:
        """The axis with its values checked against the declaration of the parameter it names."""
        holder, owner = _holder(axis, base)
        values = check_values(holder, axis.name, axis.values, owner)
        spec = next(spec for spec in parameters_of(holder) if spec.name == axis.name)
        return SweptParameter(replace(axis, values=values), spec)


def _holder(axis: SweepAxis, base: ResolvedBacktest) -> tuple[object, str]:
    """The object that declares the axis's parameter, and its name for messages."""
    if axis.target in (SweepTarget.SIGNAL, SweepTarget.ENTRY) and axis.owner:
        raise ValueError(f"{axis.key}: a {axis.target.value} parameter takes no owner")
    if axis.target is SweepTarget.SIGNAL:
        return base.signal, base.signal.name
    if axis.target is SweepTarget.ENTRY:
        return base.rules.entry, base.rules.entry.name
    if axis.target is SweepTarget.EXIT:
        return _owned_rule(axis, base.rules.exits, "exit")
    if axis.target is SweepTarget.FILTER:
        return _owned_rule(axis, base.rules.filters, "filter")
    if axis.owner not in SWEEP_SECTIONS:
        raise ValueError(f"{axis.key}: sweeps can change the settings in {', '.join(SWEEP_SECTIONS)}")
    if (axis.owner, axis.name) in NOT_SWEEPABLE:
        raise ValueError(f"{axis.key} sets the out-of-sample split, so it is the same for every combination")
    return getattr(base.settings, axis.owner), axis.owner


def _owned_rule(axis: SweepAxis, rules: Sequence[Rule], kind: str) -> tuple[Rule, str]:
    """The exit rule or filter of the backtest that the axis names as its owner."""
    rule = next((rule for rule in rules if rule.name == axis.owner), None)
    if rule is None:
        used = ", ".join(rule.name for rule in rules) or "none"
        raise ValueError(f"{axis.key}: the '{axis.owner}' {kind} is not part of this backtest (its {kind}s: {used})")
    return rule, rule.name


def _set_signal_param(setup: BacktestRequest, axis: SweepAxis, value: float) -> BacktestRequest:
    return replace(setup, params={**setup.params, axis.name: value})


def _set_entry_param(setup: BacktestRequest, axis: SweepAxis, value: float) -> BacktestRequest:
    assert setup.entry is not None, "the sweep names the entry rule first"
    return replace(setup, entry=RuleChoice(setup.entry.name, {**setup.entry.params, axis.name: value}))


def _with_param(choices: Sequence[RuleChoice], axis: SweepAxis, value: float) -> tuple[RuleChoice, ...]:
    """The rule choices with the value set on the rule the axis names as its owner."""
    return tuple(
        RuleChoice(choice.name, {**choice.params, axis.name: value}) if choice.name == axis.owner else choice
        for choice in choices
    )


def _set_exit_param(setup: BacktestRequest, axis: SweepAxis, value: float) -> BacktestRequest:
    return replace(setup, exits=_with_param(setup.exits or (), axis, value))


def _set_filter_param(setup: BacktestRequest, axis: SweepAxis, value: float) -> BacktestRequest:
    return replace(setup, filters=_with_param(setup.filters, axis, value))


def _set_setting(setup: BacktestRequest, axis: SweepAxis, value: float) -> BacktestRequest:
    section = {**setup.settings.get(axis.owner, {}), axis.name: value}
    return replace(setup, settings={**setup.settings, axis.owner: section})


# How a combination's value reaches the backtest request, by what the axis names.
_APPLY = {
    SweepTarget.SIGNAL: _set_signal_param,
    SweepTarget.ENTRY: _set_entry_param,
    SweepTarget.EXIT: _set_exit_param,
    SweepTarget.FILTER: _set_filter_param,
    SweepTarget.SETTINGS: _set_setting,
}


# ---------------------------------------------------------------------------
# Watchlist backtest


@dataclass(frozen=True)
class WatchlistBacktestRequest:
    """`setup` runs on every ticker of `universe`. Its `ticker` and `engines` are ignored: every ticker runs
    on the vectorized engine. Without a benchmark of its own, the setup takes the watchlist's."""

    universe: Watchlist
    setup: BacktestRequest


@dataclass(frozen=True)
class TickerRow:
    ticker: str
    start: pd.Timestamp
    end: pd.Timestamp
    run: TickerRun


@dataclass(frozen=True)
class PeriodSummary:
    tickers: int  # tickers that have this period
    pooled: PooledTrades  # every ticker's closed trades together
    spreads: dict[str, Spread]  # by metric name: how the tickers' values are spread


@dataclass(frozen=True)
class WatchlistBacktestReport:
    universe: Watchlist
    base: ResolvedBacktest
    rows: list[TickerRow]  # in watchlist order
    periods: dict[Period, PeriodSummary]
    missing: list[str]


METRIC_NAMES = tuple(item.name for item in fields(Metrics))


class WatchlistBacktestUseCase:
    def __init__(
        self,
        market_data: MarketData,
        settings: Settings,
        registry: SignalRegistry,
        runner: TaskRunner,
        rules: RuleCatalog = default_catalog,
    ) -> None:
        self._market_data = market_data
        self._settings = settings
        self._registry = registry
        self._runner = runner
        self._rules = rules

    def run(self, request: WatchlistBacktestRequest) -> WatchlistBacktestReport:
        universe = request.universe
        setup = replace(request.setup, benchmark=request.setup.benchmark or universe.benchmark)
        base = resolve_backtest(setup, self._settings, self._registry, self._rules)
        history = setup.period or base.settings.backtest.period
        tickers = list(universe.tickers)
        loaded = self._market_data.load([*tickers, base.benchmark] if base.benchmark else tickers, history, setup.interval)
        rules = _with_benchmark(base, loaded)
        frames = [(ticker, loaded.frames[ticker]) for ticker in tickers if ticker in loaded.frames]
        if not frames:
            raise ValueError(f"No data for any ticker of {universe.name}")

        runs = self._runner.map(TickerJob(base.signal, rules, base.config), frames)
        rows = [TickerRow(ticker, df.index[0], df.index[-1], run) for (ticker, df), run in zip(frames, runs)]
        return WatchlistBacktestReport(
            universe=universe,
            base=base,
            rows=rows,
            periods={period: _summary([row.run.period(period) for row in rows]) for period in Period},
            missing=[ticker for ticker in loaded.missing if ticker in tickers],
        )


def _summary(runs: Sequence[PeriodRun | None]) -> PeriodSummary:
    """Pooled trades and the spread of every metric over the tickers that have this period."""
    present = [run for run in runs if run is not None]
    return PeriodSummary(
        tickers=len(present),
        pooled=pool_trades(run.r_multiples for run in present),
        spreads={
            name: spread((getattr(run.metrics, name) for run in present), BREAK_EVEN.get(name)) for name in METRIC_NAMES
        },
    )


# ---------------------------------------------------------------------------
# Portfolio backtest


@dataclass(frozen=True)
class PortfolioRequest:
    """`setup` runs on every ticker of `universe` with one shared equity, on each of its `engines`; its `ticker` is
    ignored. Without a benchmark of its own, the setup takes the watchlist's, and buy & hold compares that one.

    `score_signal_params` sets the parameters of the signals a priority that scores like the scanner counts besides
    the traded one, whose parameters come from the setup; entries for the traded signal or the other direction are
    validated and change nothing."""

    universe: Watchlist
    setup: BacktestRequest
    priority: RuleChoice | None = None  # None: the default priority rule
    score_signal_params: GroupOverrides = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioRun:
    result: PortfolioResult
    full: PortfolioMetrics
    in_sample: PortfolioMetrics | None  # None when the shared calendar is too short to split
    out_of_sample: PortfolioMetrics | None
    contributions: list[TickerContribution]  # of the full history, every ticker with data in watchlist order


@dataclass(frozen=True)
class PortfolioReport:
    universe: Watchlist
    base: ResolvedBacktest
    portfolio: PortfolioConfig
    priority: PriorityRule
    benchmark: str  # compared by buy & hold, and by the filters that read a benchmark
    benchmark_close: pd.Series  # on the shared calendar, each date with the benchmark's last close at or before it
    calendar: pd.DatetimeIndex
    split: Split | None
    runs: list[PortfolioRun]
    missing: list[str]


class PortfolioUseCase:
    def __init__(
        self,
        market_data: MarketData,
        settings: Settings,
        registry: SignalRegistry,
        engines: Mapping[str, PortfolioEngineFactory],
        rules: RuleCatalog = default_catalog,
        priorities: RuleRegistry[PriorityRule] = priority_rules,
    ) -> None:
        self._market_data = market_data
        self._settings = settings
        self._registry = registry
        self._engines = engines
        self._rules = rules
        self._priorities = priorities

    @property
    def priorities(self) -> RuleRegistry[PriorityRule]:
        return self._priorities

    def run(self, request: PortfolioRequest) -> PortfolioReport:
        engines = request.setup.engines
        unknown = [name for name in engines if name not in self._engines]
        if unknown or not engines:
            raise ValueError(f"Unknown engine(s): {', '.join(unknown) or 'none given'}. Use: {', '.join(self._engines)}")
        universe = request.universe
        benchmark = _benchmark(request.setup.benchmark, universe, self._settings)
        setup = replace(request.setup, benchmark=benchmark)
        base = resolve_backtest(setup, self._settings, self._registry, self._rules)
        choice = request.priority or RuleChoice(DEFAULT_PRIORITY)
        priority = self._priorities.create(choice.name, choice.params)
        self._registry.check_params(request.score_signal_params)
        portfolio = build_portfolio_config(base.settings)

        tickers = list(universe.tickers)
        loaded = self._market_data.load([*tickers, benchmark], setup.period or base.settings.backtest.period, setup.interval)
        rules = _with_benchmark(base, loaded)
        frames = {ticker: loaded.frames[ticker] for ticker in tickers if ticker in loaded.frames}
        if not frames:
            raise ValueError(f"No data for any ticker of {universe.name}")
        if benchmark not in loaded.frames:
            raise ValueError(f"No data for the benchmark {benchmark}, which buy & hold compares")
        if priority.needs_scan:
            priority = priority.with_scan(_scan_score(frames, base, self._registry, request.score_signal_params))
        calendar = shared_calendar(frames.values())
        benchmark_close = loaded.frames[benchmark]["close"].astype(float).reindex(calendar, method="ffill")
        split = split_history(calendar, base.config.oos_pct)

        runs = [
            _portfolio_run(self._engines[name](), frames, base, rules, portfolio, priority, benchmark_close, split)
            for name in engines
        ]
        return PortfolioReport(
            universe=universe,
            base=base,
            portfolio=portfolio,
            priority=priority,
            benchmark=benchmark,
            benchmark_close=benchmark_close,
            calendar=calendar,
            split=split,
            runs=runs,
            missing=[ticker for ticker in loaded.missing if ticker in tickers],
        )


def _scan_score(
    frames: Mapping[str, pd.DataFrame], base: ResolvedBacktest, registry: SignalRegistry, params: GroupOverrides
) -> ScanScore:
    """What the score priority reads: the run's scoring, trend and fresh-bars settings and every signal of the
    traded direction, the traded one with the run's parameters and the others with `params`. Built once, for every
    engine and both periods."""
    settings, traded = base.settings, base.signal
    counted = registry.select(directions={traded.direction}, params=params)
    signals = [traded if signal.name == traded.name else signal for signal in counted]
    return ScanScore.build(
        frames, signals, traded.direction, build_scorer(settings), build_context_builder(settings), settings.scan.fresh_bars
    )


def _portfolio_run(
    engine: PortfolioEngine,
    frames: Mapping[str, pd.DataFrame],
    base: ResolvedBacktest,
    rules: TradeRules,
    portfolio: PortfolioConfig,
    priority: PriorityRule,
    benchmark_close: pd.Series,
    split: Split | None,
) -> PortfolioRun:
    """The full history and, with a split, both periods of one engine."""
    config, signal = base.config, base.signal
    result = engine.run(frames, signal, config, rules, portfolio, priority)
    full = portfolio_metrics(result, benchmark_close, config.bars_per_year)
    shares = contributions(result, config.initial_equity)
    if split is None:
        return PortfolioRun(result, full, None, None, shares)
    start = split.out_of_sample[0]
    periods = run_portfolio_periods(engine, frames, signal, config, rules, portfolio, priority, start)
    return PortfolioRun(
        result=result,
        full=full,
        in_sample=portfolio_metrics(periods.in_sample, benchmark_close, config.bars_per_year),
        out_of_sample=portfolio_metrics(periods.out_of_sample, benchmark_close, config.bars_per_year, start),
        contributions=shares,
    )


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
    sweep: SweepUseCase
    watchlist_backtest: WatchlistBacktestUseCase
    portfolio: PortfolioUseCase
    chart: ChartUseCase


def build_use_cases(
    settings: Settings,
    provider: DataProvider,
    registry: SignalRegistry = default_registry,
    engines: Mapping[str, EngineFactory] | None = None,
    runner: TaskRunner | None = None,
    rules: RuleCatalog = default_catalog,
    portfolio_engines: Mapping[str, PortfolioEngineFactory] | None = None,
) -> UseCases:
    """`runner` runs per-ticker work and sweeps; pass a `ProcessRunner` to use every core."""
    market_data = MarketData(provider, settings)
    task_runner = runner or SequentialRunner()
    return UseCases(
        scan=ScanUseCase(market_data, settings, registry, task_runner),
        market=MarketUseCase(market_data, settings, registry),
        edge=EdgeUseCase(market_data, settings, registry, task_runner),
        backtest=BacktestUseCase(market_data, settings, registry, engines or default_engines(), rules),
        sweep=SweepUseCase(market_data, settings, registry, task_runner, rules),
        watchlist_backtest=WatchlistBacktestUseCase(market_data, settings, registry, task_runner, rules),
        portfolio=PortfolioUseCase(market_data, settings, registry, portfolio_engines or default_portfolio_engines(), rules),
        chart=ChartUseCase(market_data, registry),
    )
