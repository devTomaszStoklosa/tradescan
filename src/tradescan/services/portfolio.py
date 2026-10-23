"""Portfolio backtest: one setup on every ticker of a watchlist with one shared equity."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace

import pandas as pd

from tradescan.backtest.allocation import PortfolioConfig
from tradescan.backtest.oos import Split, split_history
from tradescan.backtest.portfolio import PortfolioEngine, PortfolioResult, run_portfolio_periods, shared_calendar
from tradescan.backtest.portfolio_metrics import PortfolioMetrics, TickerContribution, contributions, portfolio_metrics
from tradescan.backtest.priority import DEFAULT_PRIORITY, PriorityRule, ScanScore, priority_rules
from tradescan.backtest.rules import RuleRegistry
from tradescan.backtest.trade_rules import RuleCatalog, RuleChoice, TradeRules, default_catalog
from tradescan.config import Settings
from tradescan.params import GroupOverrides, parameters_of
from tradescan.services.backtest import BacktestRequest, ResolvedBacktest, resolve_backtest, rules_with_benchmark
from tradescan.services.builders import build_context_builder, build_portfolio_config, build_scorer
from tradescan.services.market_data import MarketData, benchmark_ticker
from tradescan.signals.base import Direction, Signal
from tradescan.signals.registry import SignalRegistry
from tradescan.watchlist import Watchlist

PortfolioEngineFactory = Callable[[], PortfolioEngine]


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
class ScanInputs:
    """What a priority that scores like the scanner read besides the bars: the run's values of the scanner's settings
    it reads, by section as a request names them, and the signals it counted besides the traded one."""

    settings: dict[str, dict[str, object]]
    signals: tuple[Signal, ...]


@dataclass(frozen=True)
class PortfolioReport:
    universe: Watchlist
    base: ResolvedBacktest
    portfolio: PortfolioConfig
    priority: PriorityRule
    scan: ScanInputs | None  # None when the priority does not read the scanner
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
            raise ValueError(
                f"Unknown engine(s): {', '.join(unknown) or 'none given'}. Use: {', '.join(self._engines)}"
            )
        universe = request.universe
        benchmark = benchmark_ticker(request.setup.benchmark, universe, self._settings)
        setup = replace(request.setup, benchmark=benchmark)
        base = resolve_backtest(setup, self._settings, self._registry, self._rules)
        choice = request.priority or RuleChoice(DEFAULT_PRIORITY)
        priority = self._priorities.create(choice.name, choice.params)
        self._registry.check_params(request.score_signal_params)
        portfolio = build_portfolio_config(base.settings)

        tickers = list(universe.tickers)
        loaded = self._market_data.load(
            [*tickers, benchmark], setup.period or base.settings.backtest.period, setup.interval
        )
        rules = rules_with_benchmark(base, loaded)
        frames = {ticker: loaded.frames[ticker] for ticker in tickers if ticker in loaded.frames}
        if not frames:
            raise ValueError(f"No data for any ticker of {universe.name}")
        if benchmark not in loaded.frames:
            raise ValueError(f"No data for the benchmark {benchmark}, which buy & hold compares")
        scan = None
        if priority.needs_scan:
            traded = base.signal
            signals = _score_signals(traded, self._registry, request.score_signal_params)
            priority = priority.with_scan(_scan_score(frames, base.settings, signals, traded.direction))
            others = tuple(signal for signal in signals if signal.name != traded.name)
            scan = ScanInputs(settings=_score_settings(base.settings), signals=others)
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
            scan=scan,
            benchmark=benchmark,
            benchmark_close=benchmark_close,
            calendar=calendar,
            split=split,
            runs=runs,
            missing=[ticker for ticker in loaded.missing if ticker in tickers],
        )


# The settings the scanner's score reads, by section; None reads every parameter of the section.
_SCORE_SETTINGS: dict[str, tuple[str, ...] | None] = {"scoring": None, "trend": None, "scan": ("fresh_bars",)}


def _score_signals(traded: Signal, registry: SignalRegistry, params: GroupOverrides) -> list[Signal]:
    """The signals the score priority counts: every signal of the traded direction, the traded one with the run's
    parameters and the others with `params`."""
    counted = registry.select(directions={traded.direction}, params=params)
    return [traded if signal.name == traded.name else signal for signal in counted]


def _score_settings(settings: Settings) -> dict[str, dict[str, object]]:
    """The run's values of the settings the score priority reads, by section."""
    return {
        section: {
            spec.name: spec.default
            for spec in parameters_of(getattr(settings, section))
            if names is None or spec.name in names
        }
        for section, names in _SCORE_SETTINGS.items()
    }


def _scan_score(
    frames: Mapping[str, pd.DataFrame], settings: Settings, signals: Sequence[Signal], direction: Direction
) -> ScanScore:
    """What the score priority reads: the run's settings named in `_SCORE_SETTINGS` and the counted signals. Built
    once, for every engine and both periods."""
    return ScanScore.build(
        frames, signals, direction, build_scorer(settings), build_context_builder(settings), settings.scan.fresh_bars
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
