"""Walk-forward analysis: re-tune a setup on each in-sample window and trade the pick on the window after it.

The history is cut into `windows` out-of-sample windows of equal length that end on the last bar. Each one
follows an in-sample window `in_sample_ratio` times as long: of fixed length and sliding along (`rolling`),
or always from the first bar (`anchored`). On every in-sample window every combination of a sweep runs, and
the one with the highest selection metric among those with enough trades trades the next out-of-sample
window. The out-of-sample windows are stitched into one equity curve:

* each window starts with the equity the window before it ended with;
* its signal fires only within the window, so nothing it trades was known when it was picked;
* a position still open at the end of a window runs to its own exit under that window's setting, and the
  next window's setting trades from the bar of that exit on. A window can so start late, or never trade.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, fields, replace
from enum import StrEnum

import pandas as pd

from tradescan.backtest.base import BacktestEngine, Trade
from tradescan.backtest.metrics import Metrics, compute_metrics
from tradescan.backtest.oos import MIN_PERIOD_BARS, SignalBetween, SignalFrom
from tradescan.backtest.sweep import SweepCase
from tradescan.backtest.vectorized import VectorizedEngine
from tradescan.data.schema import bar_position

# Each combination runs once per in-sample window: 2000 backtests of 10 years of daily bars take 10-20 s on four cores.
MAX_RUNS = 2000

# Metrics a walk-forward can pick by, the highest first. The trade count and the exposure do not get better
# by growing, and buy & hold is the same for every combination.
SELECTION_METRICS = tuple(
    item.name for item in fields(Metrics) if item.name not in {"trades", "exposure_pct", "buy_hold_pct"}
)
DEFAULT_SELECTION_METRIC = "sharpe"


class WindowScheme(StrEnum):
    ROLLING = "rolling"  # in-sample windows of fixed length, sliding along with the out-of-sample ones
    ANCHORED = "anchored"  # in-sample windows from the first bar, growing


@dataclass(frozen=True)
class Span:
    """Bar positions from `start` up to `end` (exclusive)."""

    start: int
    end: int

    @property
    def bars(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class Window:
    in_sample: Span
    out_of_sample: Span  # starts where the in-sample window ends


@dataclass(frozen=True)
class WindowPlan:
    scheme: WindowScheme
    windows: tuple[Window, ...]
    next_in_sample: Span  # the in-sample window that ends on the last bar: it picks the setting to trade next

    @property
    def in_samples(self) -> tuple[Span, ...]:
        """Every in-sample window, the next one last."""
        return (*(window.in_sample for window in self.windows), self.next_in_sample)

    @property
    def start(self) -> int:
        """The first out-of-sample bar."""
        return self.windows[0].out_of_sample.start


def plan_windows(bars: int, windows: int, in_sample_ratio: float, scheme: WindowScheme) -> WindowPlan:
    """`windows` out-of-sample windows that end on the last bar, each after its in-sample window.

    Bars before the first in-sample window (fewer than `windows + in_sample_ratio`) only warm indicators up.
    """
    if windows < 1 or in_sample_ratio < 1:
        raise ValueError("A walk-forward needs at least one window and in-sample windows at least as long")
    length = math.floor(bars / (windows + in_sample_ratio))
    in_sample = math.floor(in_sample_ratio * length)
    if length < MIN_PERIOD_BARS:
        needed = math.ceil(MIN_PERIOD_BARS * (windows + in_sample_ratio))
        raise ValueError(
            f"{bars} bars are too few for {windows} windows with in-sample windows {in_sample_ratio:g} times as long: "
            f"every window needs at least {MIN_PERIOD_BARS} bars, so at least {needed} bars"
        )
    first = bars - windows * length

    def in_sample_before(end: int) -> Span:
        return Span(0 if scheme is WindowScheme.ANCHORED else end - in_sample, end)

    starts = [first + position * length for position in range(windows)]
    return WindowPlan(
        scheme=scheme,
        windows=tuple(Window(in_sample_before(start), Span(start, start + length)) for start in starts),
        next_in_sample=in_sample_before(bars),
    )


def in_sample_metrics(engine: BacktestEngine, ticker: str, df: pd.DataFrame, case: SweepCase, span: Span) -> Metrics:
    """The combination on one in-sample window: the engine gets the bars up to its end, the signal fires from its
    start (earlier bars warm indicators up), and the metrics start at its first bar."""
    signal = SignalFrom(case.signal, span.start) if span.start else case.signal
    result = engine.run(ticker, df.iloc[: span.end], signal, case.config, case.rules)
    close = df["close"].iloc[span.start : span.end]
    return compute_metrics(result.equity.iloc[span.start :], result.trades, close, case.config.bars_per_year)


@dataclass(frozen=True)
class InSampleJob:
    """Runs one combination on every in-sample window. A module-level callable, so worker processes can unpickle it."""

    ticker: str
    df: pd.DataFrame
    spans: tuple[Span, ...]

    def __call__(self, case: SweepCase) -> tuple[Metrics, ...]:
        engine = VectorizedEngine()
        return tuple(in_sample_metrics(engine, self.ticker, self.df, case, span) for span in self.spans)


def qualifies(metrics: Metrics | None, metric: str, min_trades: int) -> bool:
    """Whether a combination's in-sample result can be picked: it ran, has a value and enough closed trades."""
    return metrics is not None and metrics.trades >= min_trades and not math.isnan(getattr(metrics, metric))


def pick(results: Sequence[Metrics | None], metric: str, min_trades: int) -> int | None:
    """The position of the highest `metric` among the results that qualify; ties go to the first. None when
    none qualifies. A combination that could not run is None."""
    best: int | None = None
    for position, metrics in enumerate(results):
        if not qualifies(metrics, metric, min_trades):
            continue
        if best is None or getattr(metrics, metric) > getattr(results[best], metric):
            best = position
    return best


@dataclass(frozen=True, eq=False)  # holds a Series, which compares element by element
class Segment:
    """The bars one window's setting owns in the stitched curve, both ends included: from the bar it starts
    trading from to the bar the next window takes over (the last bar for the last window)."""

    start: int
    end: int
    equity: pd.Series
    trades: tuple[Trade, ...]

    @property
    def traded(self) -> bool:
        """False when the window had no bars of its own, because the window before it was still in a trade."""
        return self.end > self.start


@dataclass(frozen=True, eq=False)  # holds a Series, which compares element by element
class StitchedRun:
    equity: pd.Series  # from the first out-of-sample bar to the last bar
    trades: tuple[Trade, ...]
    segments: tuple[Segment, ...]  # one per window


def stitch(
    engine: BacktestEngine,
    ticker: str,
    df: pd.DataFrame,
    plan: WindowPlan,
    picks: Sequence[SweepCase | None],
    initial_equity: float,
) -> StitchedRun:
    """Each window's pick traded on its out-of-sample window, one after the other (see the module docstring).
    A window without a pick holds cash."""
    last = len(df) - 1
    start = plan.start
    equity = initial_equity
    pieces: list[pd.Series] = []
    segments: list[Segment] = []
    for position, (window, case) in enumerate(zip(plan.windows, picks, strict=True)):
        is_last = position == len(plan.windows) - 1
        end = window.out_of_sample.end
        trades: tuple[Trade, ...] = ()
        curve = pd.Series(equity, index=df.index, name="equity")
        if case is not None and start < end:
            config = replace(case.config, initial_equity=equity)
            result = engine.run(ticker, df, SignalBetween(case.signal, start, end), config, case.rules)
            trades, curve = result.trades, result.equity
        exits = [bar_position(df.index, trade.exit_date) for trade in trades]
        takeover = last if is_last else min(last, max(start, end, *exits))
        part = curve.iloc[start : takeover + 1]
        segments.append(Segment(start, takeover, part, trades))
        pieces.append(part if is_last else part.iloc[:-1])  # the next window starts with the same value
        equity = float(part.iloc[-1])
        start = takeover
    stitched = pd.concat(pieces).rename("equity")
    return StitchedRun(stitched, tuple(trade for segment in segments for trade in segment.trades), tuple(segments))


def segment_metrics(segment: Segment, df: pd.DataFrame, bars_per_year: int) -> Metrics | None:
    """The metrics of the bars a window's setting owned; None when it owned none."""
    if not segment.traded:
        return None
    close = df["close"].iloc[segment.start : segment.end + 1]
    return compute_metrics(segment.equity, segment.trades, close, bars_per_year)


def efficiency(out_of_sample: Metrics, in_sample: Sequence[Metrics]) -> float:
    """Walk-forward efficiency (Pardo): the stitched out-of-sample CAGR over the average in-sample CAGR of the
    picks. NaN when the picks did not gain in-sample on average."""
    values = [metrics.cagr_pct for metrics in in_sample if math.isfinite(metrics.cagr_pct)]
    average = sum(values) / len(values) if values else math.nan
    if not average > 0:
        return math.nan
    return out_of_sample.cagr_pct / average
