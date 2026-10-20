"""Sweep: one backtest setup rerun over a grid of one or two parameters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TypeVar

import pandas as pd

from tradescan.backtest.oos import MIN_PERIOD_BARS, PeriodMetrics, Split, split_history
from tradescan.backtest.rules import Rule
from tradescan.backtest.sweep import SweepAxis, SweepCase, SweepJob, SweepTarget, check_axes, grid
from tradescan.backtest.trade_rules import RuleCatalog, RuleChoice, default_catalog
from tradescan.config import Settings
from tradescan.data.schema import bar_dates
from tradescan.parallel import TaskRunner
from tradescan.params import ParamSpec, check_values, parameters_of
from tradescan.services.backtest import BacktestRequest, ResolvedBacktest, load_setup, resolve_backtest
from tradescan.services.market_data import MarketData
from tradescan.signals.registry import SignalRegistry

T = TypeVar("T")


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


# Settings sections a backtest reads, and the settings a sweep cannot vary with the reason why.
SWEEP_SECTIONS = ("account", "risk", "backtest", "pyramid")
NOT_SWEEPABLE = {("backtest", "oos_pct"): "sets the out-of-sample split, so it is the same for every combination"}


@dataclass(frozen=True)
class Combination:
    """One combination of the swept values and its backtest inputs."""

    values: tuple[float, ...]  # one per axis
    case: SweepCase | None  # None when the combination breaks a rule between parameters
    error: str | None = None


@dataclass(frozen=True)
class SweepGrid:
    """A setup resolved and loaded, with every combination of its swept values."""

    ticker: str
    base: ResolvedBacktest
    base_case: SweepCase  # the setup itself, with the benchmark's closes
    parameters: tuple[SweptParameter, ...]
    df: pd.DataFrame
    combinations: tuple[Combination, ...]  # the first axis changes slowest

    @property
    def cases(self) -> list[SweepCase]:
        """The combinations that can run, in grid order."""
        return [item.case for item in self.combinations if item.case is not None]

    def per_combination(self, results: Sequence[T]) -> list[T | None]:
        """The results of `cases`, one per combination: None where a combination could not run."""
        remaining = iter(results)
        return [next(remaining) if item.case is not None else None for item in self.combinations]


class SweepGridBuilder:
    """Turns a setup and its swept axes into a `SweepGrid`. Shared by the sweep and the walk-forward, which
    each name the settings they cannot vary."""

    def __init__(
        self,
        market_data: MarketData,
        settings: Settings,
        registry: SignalRegistry,
        rules: RuleCatalog = default_catalog,
    ) -> None:
        self._market_data = market_data
        self._settings = settings
        self._registry = registry
        self._rules = rules

    def build(
        self, setup: BacktestRequest, axes: Sequence[SweepAxis], fixed: Mapping[tuple[str, str], str]
    ) -> SweepGrid:
        """`fixed` maps (section, name) of the settings that cannot be swept to why not."""
        check_axes(axes)
        setup = self._named_rules(setup)
        base = resolve_backtest(setup, self._settings, self._registry, self._rules)
        parameters = tuple(self._check(axis, base, fixed) for axis in axes)
        checked = tuple(parameter.axis for parameter in parameters)

        ticker = setup.ticker.upper()
        period = setup.period or base.settings.backtest.period
        df, base_rules = load_setup(self._market_data, ticker, base, period, setup.interval)
        combinations: list[Combination] = []
        for values in grid(checked):
            combination = setup
            for axis, value in zip(checked, values, strict=True):
                combination = _APPLY[axis.target](combination, axis, value)
            try:
                resolved = resolve_backtest(combination, self._settings, self._registry, self._rules)
            except ValueError as error:
                combinations.append(Combination(values, None, str(error)))
                continue
            rules = resolved.rules.with_benchmark(base_rules.benchmark_close)  # no axis changes the benchmark
            combinations.append(Combination(values, SweepCase(resolved.signal, rules, resolved.config)))
        return SweepGrid(
            ticker=ticker,
            base=base,
            base_case=SweepCase(base.signal, base_rules, base.config),
            parameters=parameters,
            df=df,
            combinations=tuple(combinations),
        )

    def _named_rules(self, setup: BacktestRequest) -> BacktestRequest:
        """The setup with its entry and exits named, so axes can refer to the default rules too."""
        exits = (
            setup.exits if setup.exits is not None else tuple(RuleChoice(name) for name in self._rules.default_exits)
        )
        return replace(setup, entry=setup.entry or RuleChoice(self._rules.default_entry), exits=exits)

    def _check(self, axis: SweepAxis, base: ResolvedBacktest, fixed: Mapping[tuple[str, str], str]) -> SweptParameter:
        """The axis with its values checked against the declaration of the parameter it names."""
        holder, owner = _holder(axis, base, fixed)
        values = check_values(holder, axis.name, axis.values, owner)
        spec = next(spec for spec in parameters_of(holder) if spec.name == axis.name)
        return SweptParameter(replace(axis, values=values), spec)


class SweepUseCase:
    def __init__(self, grids: SweepGridBuilder, runner: TaskRunner) -> None:
        self._grids = grids
        self._runner = runner

    def run(self, request: SweepRequest) -> SweepReport:
        sweep = self._grids.build(request.setup, request.axes, NOT_SWEEPABLE)
        ticker, df, config = sweep.ticker, sweep.df, sweep.base.config
        split = split_history(bar_dates(df), config.oos_pct)
        if split is None:
            raise ValueError(
                f"{ticker} has {len(df)} bars: too few to split at {config.oos_pct:g}% "
                f"with at least {MIN_PERIOD_BARS} bars in each period. Use a longer history."
            )
        results = sweep.per_combination(self._runner.map(SweepJob(ticker, df, split.index), sweep.cases))
        cells = [
            SweepCell(item.values, periods, item.error)
            for item, periods in zip(sweep.combinations, results, strict=True)
        ]
        return SweepReport(
            ticker=ticker, base=sweep.base, parameters=sweep.parameters, close=df["close"], split=split, cells=cells
        )


def _holder(axis: SweepAxis, base: ResolvedBacktest, fixed: Mapping[tuple[str, str], str]) -> tuple[object, str]:
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
    if (axis.owner, axis.name) in fixed:
        raise ValueError(f"{axis.key} {fixed[(axis.owner, axis.name)]}")
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
