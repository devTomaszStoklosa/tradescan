"""Scanner: turns OHLCV frames into ranked, risk-planned signal hits."""

from __future__ import annotations

import math
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

import pandas as pd

from tradescan.backtest.edge import EdgeAnalyzer, EdgeStats
from tradescan.context import ContextBuilder, TickerContext
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


class Scanner:
    def __init__(
        self,
        signals: Sequence[Signal],
        context_builder: ContextBuilder,
        scorer: Scorer,
        risk_planner: RiskPlanner,
        edge_analyzer: EdgeAnalyzer,
        fresh_bars: int = 3,
        min_bars: int = 60,
    ) -> None:
        self._signals = list(signals)
        self._context_builder = context_builder
        self._scorer = scorer
        self._risk_planner = risk_planner
        self._edge_analyzer = edge_analyzer
        self._fresh_bars = fresh_bars
        self._min_bars = min_bars

    def scan(self, frames: Mapping[str, pd.DataFrame]) -> ScanResult:
        contexts: dict[str, TickerContext] = {}
        fired: dict[str, list[FiredSignal]] = {}
        skipped: list[str] = []
        for ticker, df in frames.items():
            if len(df) < self._min_bars:
                skipped.append(ticker)
                continue
            contexts[ticker] = self._context_builder.build(ticker, df)
            fired[ticker] = self._fresh_signals(df)

        percentiles = rs_percentiles({ticker: context.rs_raw for ticker, context in contexts.items()})
        hits = [
            self._hit(ticker, direction, matching, contexts[ticker], percentiles.get(ticker, math.nan), frames[ticker])
            for ticker, signals in fired.items()
            for direction in Direction
            if (matching := [item for item in signals if item.signal.direction is direction])
        ]
        hits.sort(key=lambda hit: hit.score.total, reverse=True)
        return ScanResult(hits=hits, skipped=skipped)

    def _fresh_signals(self, df: pd.DataFrame) -> list[FiredSignal]:
        fresh = []
        for signal in self._signals:
            bars_ago = bars_since_last(signal.events(df), self._fresh_bars)
            if bars_ago is not None:
                fresh.append(FiredSignal(signal=signal, bars_ago=bars_ago))
        return fresh

    def _hit(
        self,
        ticker: str,
        direction: Direction,
        fired: list[FiredSignal],
        context: TickerContext,
        rs_percentile: float,
        df: pd.DataFrame,
    ) -> ScanHit:
        fired.sort(key=lambda item: (item.bars_ago, -self._scorer.weight(item.signal)))
        primary = fired[0].signal  # most recent, then heaviest: the signal the edge column describes
        return ScanHit(
            ticker=ticker,
            direction=direction,
            fired=tuple(fired),
            score=self._scorer.score(direction, [item.signal for item in fired], context, rs_percentile),
            context=context,
            rs_percentile=rs_percentile,
            risk=self._risk_planner.plan(direction, context.close, context.atr),
            edge=self._edge_analyzer.analyze([df], primary),
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
    return [
        hit
        for hit in hits
        if hit.score.total >= min_score and (not directions or hit.direction in directions)
    ]
