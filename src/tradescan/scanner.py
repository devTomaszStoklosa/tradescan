"""Scanner: turns OHLCV frames into ranked, risk-planned signal hits."""

from __future__ import annotations

import math
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

import pandas as pd

from tradescan.backtest.edge import EdgeStats, combine_samples, edge_samples
from tradescan.context import ContextBuilder, TickerContext
from tradescan.parallel import SequentialRunner, TaskRunner
from tradescan.risk import RiskPlan, RiskPlanner
from tradescan.scoring import ScoreBreakdown, Scorer
from tradescan.signals.base import Direction, Signal
from tradescan.signals.conditions import bars_since_last


@dataclass(frozen=True)
class FiredSignal:
    signal: Signal
    bars_ago: int


@dataclass(frozen=True)
class ScanHit:
    ticker: str
    direction: Direction
    fired: tuple[FiredSignal, ...]
    score: ScoreBreakdown
    context: TickerContext
    rs_percentile: float
    risk: RiskPlan
    edge: EdgeStats | None


@dataclass(frozen=True)
class ScanResult:
    hits: list[ScanHit]
    skipped: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TickerAnalysis:
    """Everything the scan needs from one ticker that does not depend on the other tickers."""

    ticker: str
    context: TickerContext
    fired: dict[Direction, tuple[FiredSignal, ...]]  # most recent, then heaviest first
    edges: dict[Direction, EdgeStats]


@dataclass(frozen=True)
class TickerAnalyzer:
    """Per-ticker job for task runners. A module-level dataclass, so it can be sent to worker processes."""

    signals: tuple[Signal, ...]
    context_builder: ContextBuilder
    scorer: Scorer
    fresh_bars: int
    edge_horizon: int

    def __call__(self, item: tuple[str, pd.DataFrame]) -> TickerAnalysis:
        ticker, df = item
        events = {signal: signal.events(df) for signal in self.signals}
        fired: dict[Direction, list[FiredSignal]] = {}
        for signal, flags in events.items():
            bars_ago = bars_since_last(flags, self.fresh_bars)
            if bars_ago is not None:
                fired.setdefault(signal.direction, []).append(FiredSignal(signal=signal, bars_ago=bars_ago))

        ordered = {
            direction: tuple(sorted(items, key=lambda item: (item.bars_ago, -self.scorer.weight(item.signal))))
            for direction, items in fired.items()
        }
        edges = {}
        for direction, items in ordered.items():
            primary = items[0].signal  # the signal the edge column describes
            sample = edge_samples(df, primary, (self.edge_horizon,), events[primary])[0]
            edges[direction] = combine_samples(primary.name, self.edge_horizon, [sample])
        return TickerAnalysis(ticker=ticker, context=self.context_builder.build(ticker, df), fired=ordered, edges=edges)


class Scanner:
    def __init__(
        self,
        signals: Sequence[Signal],
        context_builder: ContextBuilder,
        scorer: Scorer,
        risk_planner: RiskPlanner,
        edge_horizon: int = 10,
        fresh_bars: int = 3,
        min_bars: int = 60,
        runner: TaskRunner | None = None,
    ) -> None:
        self._analyzer = TickerAnalyzer(
            signals=tuple(signals),
            context_builder=context_builder,
            scorer=scorer,
            fresh_bars=fresh_bars,
            edge_horizon=edge_horizon,
        )
        self._scorer = scorer
        self._risk_planner = risk_planner
        self._min_bars = min_bars
        self._runner = runner or SequentialRunner()

    def scan(self, frames: Mapping[str, pd.DataFrame]) -> ScanResult:
        skipped = [ticker for ticker, df in frames.items() if len(df) < self._min_bars]
        eligible = [(ticker, df) for ticker, df in frames.items() if len(df) >= self._min_bars]
        analyses = self._runner.map(self._analyzer, eligible)

        percentiles = rs_percentiles({analysis.ticker: analysis.context.rs_raw for analysis in analyses})
        hits = [
            self._hit(analysis, direction, percentiles.get(analysis.ticker, math.nan))
            for analysis in analyses
            for direction in Direction
            if direction in analysis.fired
        ]
        hits.sort(key=lambda hit: hit.score.total, reverse=True)
        return ScanResult(hits=hits, skipped=skipped)

    def _hit(self, analysis: TickerAnalysis, direction: Direction, rs_percentile: float) -> ScanHit:
        fired = analysis.fired[direction]
        context = analysis.context
        return ScanHit(
            ticker=analysis.ticker,
            direction=direction,
            fired=fired,
            score=self._scorer.score(direction, [item.signal for item in fired], context, rs_percentile),
            context=context,
            rs_percentile=rs_percentile,
            risk=self._risk_planner.plan(direction, context.close, context.atr),
            edge=analysis.edges.get(direction),
        )


def rs_percentiles(raw: Mapping[str, float]) -> dict[str, float]:
    """Percentile rank (0-100) of each ticker's raw relative strength within the scanned universe."""
    values = pd.Series(raw, dtype=float).dropna()
    if values.empty:
        return {}
    return (values.rank(pct=True) * 100.0).to_dict()


def filter_hits(
    hits: Iterable[ScanHit],
    min_score: float = -math.inf,
    directions: Collection[Direction] | None = None,
) -> list[ScanHit]:
    return [hit for hit in hits if hit.score.total >= min_score and (not directions or hit.direction in directions)]
