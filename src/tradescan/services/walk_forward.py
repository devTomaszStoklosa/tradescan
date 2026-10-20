"""Walk-forward: re-tune a setup on rolling windows and trade each pick on the window after it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from tradescan.backtest.base import BacktestEngine, BacktestResult
from tradescan.backtest.metrics import Metrics, compute_metrics
from tradescan.backtest.oos import SignalFrom
from tradescan.backtest.sweep import SweepAxis
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.backtest.walk_forward import (
    DEFAULT_SELECTION_METRIC,
    MAX_RUNS,
    SELECTION_METRICS,
    InSampleJob,
    Segment,
    Span,
    StitchedRun,
    Window,
    WindowPlan,
    WindowScheme,
    efficiency,
    pick,
    plan_windows,
    qualifies,
    segment_metrics,
    stitch,
)
from tradescan.config import WalkForwardSettings
from tradescan.parallel import TaskRunner
from tradescan.services.backtest import BacktestRequest, ResolvedBacktest
from tradescan.services.sweep import Combination, SweepGridBuilder, SweptParameter

# The windows split the history and carry the equity from one to the next, so neither can be swept.
NOT_WALKABLE = {
    ("backtest", "oos_pct"): "has no effect in a walk-forward, whose windows split the history",
    ("account", "equity"): "is carried from window to window in a walk-forward",
}


@dataclass(frozen=True)
class WalkForwardRequest:
    """`setup` and `axes` as in a sweep; the setup's `walk_forward` settings set the windows, their in-sample
    length and the trades a pick needs. Its `engines` are ignored: walk-forwards run on the vectorized engine."""

    setup: BacktestRequest
    axes: tuple[SweepAxis, ...]
    scheme: WindowScheme = WindowScheme.ROLLING
    metric: str = DEFAULT_SELECTION_METRIC


@dataclass(frozen=True)
class WindowPick:
    """What one in-sample window picked."""

    span: Span
    combination: int | None  # position in the grid; None when no combination qualified
    in_sample: Metrics | None  # the pick's in-sample metrics
    qualified: int  # combinations it could pick from


@dataclass(frozen=True)
class WalkForwardWindow:
    window: Window
    pick: WindowPick
    segment: Segment
    out_of_sample: Metrics | None  # of the bars its setting owned; None when it owned none


@dataclass(frozen=True)
class WalkForwardReport:
    ticker: str
    base: ResolvedBacktest
    parameters: tuple[SweptParameter, ...]
    combinations: tuple[Combination, ...]
    settings: WalkForwardSettings
    plan: WindowPlan
    metric: str
    close: pd.Series
    windows: list[WalkForwardWindow]
    next_pick: WindowPick  # of the in-sample window that ends on the last bar: the setting to trade next
    stitched: StitchedRun
    metrics: Metrics  # of the stitched curve
    unchanged: BacktestResult  # the setup as given, traded from the first out-of-sample bar on
    unchanged_metrics: Metrics  # from the first out-of-sample bar on
    efficiency: float  # NaN when the picks did not gain in-sample on average


class WalkForwardUseCase:
    def __init__(self, grids: SweepGridBuilder, runner: TaskRunner, engine: BacktestEngine | None = None) -> None:
        self._grids = grids
        self._runner = runner
        self._engine = engine or VectorizedEngine()

    def run(self, request: WalkForwardRequest) -> WalkForwardReport:
        if request.metric not in SELECTION_METRICS:
            raise ValueError(f"Unknown selection metric '{request.metric}'. Use: {', '.join(SELECTION_METRICS)}")
        sweep = self._grids.build(request.setup, request.axes, NOT_WALKABLE)
        ticker, df, base = sweep.ticker, sweep.df, sweep.base
        settings = base.settings.walk_forward
        try:
            plan = plan_windows(len(df), settings.windows, settings.in_sample_ratio, request.scheme)
        except ValueError as error:
            raise ValueError(f"{ticker}: {error}. Use a longer history or fewer windows.") from None
        cases = sweep.cases
        runs = len(cases) * len(plan.in_samples)
        if runs > MAX_RUNS:
            raise ValueError(
                f"{len(cases)} combinations on {len(plan.in_samples)} in-sample windows (the next one included) are "
                f"{runs} backtests; a walk-forward runs at most {MAX_RUNS}. Sweep fewer values or use fewer windows."
            )

        results = sweep.per_combination(self._runner.map(InSampleJob(ticker, df, plan.in_samples), cases))
        picks = [
            _pick_window(results, position, span, request.metric, settings.min_trades)
            for position, span in enumerate(plan.in_samples)
        ]
        *window_picks, next_pick = picks
        picked = [
            sweep.combinations[item.combination].case if item.combination is not None else None for item in window_picks
        ]
        stitched = stitch(self._engine, ticker, df, plan, picked, base.config.initial_equity)

        bars_per_year = base.config.bars_per_year
        close = df["close"].iloc[plan.start :]
        metrics = compute_metrics(stitched.equity, stitched.trades, close, bars_per_year)
        unchanged = self._engine.run(
            ticker, df, SignalFrom(base.signal, plan.start), base.config, sweep.base_case.rules
        )
        return WalkForwardReport(
            ticker=ticker,
            base=base,
            parameters=sweep.parameters,
            combinations=sweep.combinations,
            settings=settings,
            plan=plan,
            metric=request.metric,
            close=df["close"],
            windows=[
                WalkForwardWindow(window, item, segment, segment_metrics(segment, df, bars_per_year))
                for window, item, segment in zip(plan.windows, window_picks, stitched.segments, strict=True)
            ],
            next_pick=next_pick,
            stitched=stitched,
            metrics=metrics,
            unchanged=unchanged,
            unchanged_metrics=compute_metrics(
                unchanged.equity.iloc[plan.start :], unchanged.trades, close, bars_per_year
            ),
            efficiency=efficiency(metrics, [item.in_sample for item in window_picks if item.in_sample is not None]),
        )


def _pick_window(
    results: Sequence[tuple[Metrics, ...] | None], position: int, span: Span, metric: str, min_trades: int
) -> WindowPick:
    """The pick of the in-sample window at `position`, from every combination's results on that window."""
    window = [result[position] if result is not None else None for result in results]
    best = pick(window, metric, min_trades)
    return WindowPick(
        span=span,
        combination=best,
        in_sample=window[best] if best is not None else None,
        qualified=sum(qualifies(metrics, metric, min_trades) for metrics in window),
    )
