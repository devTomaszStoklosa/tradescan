"""Rotation sweep: one rotation setup rerun over a grid of one or two parameters."""

from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd

from tradescan.backtest.oos import MIN_PERIOD_BARS, Split, split_history
from tradescan.backtest.priority import PriorityRule, priority_rules
from tradescan.backtest.rotation import DEFAULT_RANKING, VectorizedRotationEngine
from tradescan.backtest.rotation_sweep import (
    RotationPeriodMetrics,
    RotationSweepAxis,
    RotationSweepCase,
    RotationSweepJob,
    RotationSweepTarget,
)
from tradescan.backtest.rules import RuleRegistry
from tradescan.backtest.sweep import check_axes, grid
from tradescan.backtest.trade_rules import RuleChoice
from tradescan.backtest.weighting import DEFAULT_WEIGHTING, WeightRule, weight_rules
from tradescan.config import Settings
from tradescan.data.schema import bar_dates
from tradescan.parallel import TaskRunner
from tradescan.params import ParamSpec, check_values, parameters_of
from tradescan.services.market_data import MarketData
from tradescan.services.rotation import (
    NO_REBALANCE,
    ResolvedRotation,
    RotationRequest,
    load_rotation,
    resolve_rotation,
)
from tradescan.services.sweep import NOT_SWEEPABLE
from tradescan.watchlist import Watchlist

# Settings sections a rotation reads; the settings a sweep cannot vary are the backtest sweep's.
ROTATION_SWEEP_SECTIONS = ("rotation", "backtest")


@dataclass(frozen=True)
class RotationSweepRequest:
    """`setup` is the rotation every combination starts from. Its `engines` are ignored: sweeps run on the
    vectorized engine, which gives the same trades as Cerebro many times faster."""

    setup: RotationRequest
    axes: tuple[RotationSweepAxis, ...]


@dataclass(frozen=True)
class RotationSweptParameter:
    axis: RotationSweepAxis  # with validated values
    spec: ParamSpec  # the declaration; its default is the setup's own value


@dataclass(frozen=True)
class RotationSweepCell:
    values: tuple[float, ...]  # one per axis
    periods: RotationPeriodMetrics | None
    error: str | None = None  # why this combination could not run, e.g. a cross-field rule


@dataclass(frozen=True)
class RotationSweepReport:
    universe: Watchlist
    base: ResolvedRotation  # the setup every combination starts from
    parameters: tuple[RotationSweptParameter, ...]
    dates: pd.DatetimeIndex  # the setup's run: from its first rebalance with a pick
    split: Split  # of the setup's run, the same for every combination
    cells: list[RotationSweepCell]  # the first axis changes slowest
    missing: list[str]


@dataclass(frozen=True)
class _Combination:
    values: tuple[float, ...]
    case: RotationSweepCase | None  # None when the combination breaks a rule between parameters
    error: str | None = None


class RotationSweepUseCase:
    def __init__(
        self,
        market_data: MarketData,
        settings: Settings,
        runner: TaskRunner,
        priorities: RuleRegistry[PriorityRule] = priority_rules,
        weightings: RuleRegistry[WeightRule] = weight_rules,
    ) -> None:
        self._market_data = market_data
        self._settings = settings
        self._runner = runner
        self._priorities = priorities
        self._weightings = weightings

    def run(self, request: RotationSweepRequest) -> RotationSweepReport:
        check_axes(request.axes)
        setup = _named_rules(request.setup)
        base = self._resolve(setup)
        parameters = tuple(_check(axis, base) for axis in request.axes)
        checked = tuple(parameter.axis for parameter in parameters)
        data = load_rotation(self._market_data, setup, base)

        # The setup's own run sets the split, as on a rotation run, so the setup's cell matches that run's periods.
        first = VectorizedRotationEngine().run(
            data.frames, base.config, base.rotation, base.ranking, base.weighting, data.safe_frame
        )
        if not first.rebalances:
            raise ValueError(NO_REBALANCE)
        dates = bar_dates(first.equity)
        split = split_history(dates, base.config.oos_pct)
        if split is None:
            raise ValueError(
                f"The rotation runs {len(dates)} bars: too few to split at {base.config.oos_pct:g}% "
                f"with at least {MIN_PERIOD_BARS} bars in each period. Use a longer history."
            )

        combinations = [self._combination(setup, checked, values) for values in grid(checked)]
        job = RotationSweepJob(data.frames, data.safe_frame, data.benchmark_close, split.out_of_sample[0])
        results = iter(self._runner.map(job, [item.case for item in combinations if item.case is not None]))
        cells = [
            _cell(item.values, next(results))
            if item.case is not None
            else RotationSweepCell(item.values, None, item.error)
            for item in combinations
        ]
        return RotationSweepReport(
            universe=setup.universe,
            base=base,
            parameters=parameters,
            dates=dates,
            split=split,
            cells=cells,
            missing=data.missing,
        )

    def _resolve(self, setup: RotationRequest) -> ResolvedRotation:
        return resolve_rotation(setup, self._settings, self._priorities, self._weightings)

    def _combination(
        self, setup: RotationRequest, axes: tuple[RotationSweepAxis, ...], values: tuple[float, ...]
    ) -> _Combination:
        combination = setup
        for axis, value in zip(axes, values, strict=True):
            combination = _APPLY[axis.target](combination, axis, value)
        try:
            resolved = self._resolve(combination)
        except ValueError as error:
            return _Combination(values, None, str(error))
        return _Combination(
            values, RotationSweepCase(resolved.config, resolved.rotation, resolved.ranking, resolved.weighting)
        )


def _cell(values: tuple[float, ...], periods: RotationPeriodMetrics) -> RotationSweepCell:
    """A combination whose lookbacks never let a period pick a ticker has nothing to show for that period."""
    for name, period in (("in-sample", periods.in_sample), ("out-of-sample", periods.out_of_sample)):
        if not period.stats.rebalances:
            return RotationSweepCell(
                values, None, f"No {name} rebalance had a ticker to pick: a lookback is longer than the {name} history"
            )
    return RotationSweepCell(values, periods)


def _named_rules(setup: RotationRequest) -> RotationRequest:
    """The setup with its ranking and weighting named, so axes can refer to the default rules too."""
    return replace(
        setup,
        ranking=setup.ranking or RuleChoice(DEFAULT_RANKING),
        weighting=setup.weighting or RuleChoice(DEFAULT_WEIGHTING),
    )


def _check(axis: RotationSweepAxis, base: ResolvedRotation) -> RotationSweptParameter:
    """The axis with its values checked against the declaration of the parameter it names."""
    holder, owner = _holder(axis, base)
    values = check_values(holder, axis.name, axis.values, owner)
    spec = next(spec for spec in parameters_of(holder) if spec.name == axis.name)
    return RotationSweptParameter(replace(axis, values=values), spec)


def _holder(axis: RotationSweepAxis, base: ResolvedRotation) -> tuple[object, str]:
    """The object that declares the axis's parameter, and its name for messages."""
    if axis.target is not RotationSweepTarget.SETTINGS and axis.owner:
        raise ValueError(f"{axis.key}: a {axis.target.value} parameter takes no owner")
    if axis.target is RotationSweepTarget.RANKING:
        return base.ranking, base.ranking.name
    if axis.target is RotationSweepTarget.WEIGHTING:
        return base.weighting, base.weighting.name
    if axis.owner not in ROTATION_SWEEP_SECTIONS:
        raise ValueError(f"{axis.key}: rotation sweeps can change the settings in {', '.join(ROTATION_SWEEP_SECTIONS)}")
    if (axis.owner, axis.name) in NOT_SWEEPABLE:
        raise ValueError(f"{axis.key} {NOT_SWEEPABLE[(axis.owner, axis.name)]}")
    return getattr(base.settings, axis.owner), axis.owner


def _with_param(choice: RuleChoice | None, axis: RotationSweepAxis, value: float) -> RuleChoice:
    assert choice is not None, "the sweep names the ranking and the weighting first"
    return RuleChoice(choice.name, {**choice.params, axis.name: value})


def _set_ranking_param(setup: RotationRequest, axis: RotationSweepAxis, value: float) -> RotationRequest:
    return replace(setup, ranking=_with_param(setup.ranking, axis, value))


def _set_weighting_param(setup: RotationRequest, axis: RotationSweepAxis, value: float) -> RotationRequest:
    return replace(setup, weighting=_with_param(setup.weighting, axis, value))


def _set_setting(setup: RotationRequest, axis: RotationSweepAxis, value: float) -> RotationRequest:
    section = {**setup.settings.get(axis.owner, {}), axis.name: value}
    return replace(setup, settings={**setup.settings, axis.owner: section})


# How a combination's value reaches the rotation request, by what the axis names.
_APPLY = {
    RotationSweepTarget.RANKING: _set_ranking_param,
    RotationSweepTarget.WEIGHTING: _set_weighting_param,
    RotationSweepTarget.SETTINGS: _set_setting,
}
