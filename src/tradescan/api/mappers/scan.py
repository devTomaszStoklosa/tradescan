"""Map a scan report."""

from __future__ import annotations

from tradescan.api.mappers.common import day, finite
from tradescan.api.mappers.edge import edge_stats_out
from tradescan.api.mappers.market import regime_out
from tradescan.api.schemas.scan import FiredSignalOut, HitOut, RiskOut, ScanOut, ScoreOut
from tradescan.scanner import ScanHit
from tradescan.scoring import Scorer
from tradescan.services.scan import ScanReport


def hit_out(hit: ScanHit, scorer: Scorer) -> HitOut:
    context, risk, score = hit.context, hit.risk, hit.score
    return HitOut(
        ticker=hit.ticker,
        direction=hit.direction,
        date=day(context.date),
        close=context.close,
        change_pct=finite(context.change_pct),
        atr=finite(context.atr),
        atr_pct=finite(context.atr_pct),
        adx=finite(context.adx),
        daily_trend=context.daily_trend.value,
        weekly_trend=context.weekly_trend.value,
        rs_percentile=finite(hit.rs_percentile),
        fired=[
            FiredSignalOut(
                name=item.signal.name,
                family=item.signal.family,
                bars_ago=item.bars_ago,
                weight=scorer.weight(item.signal),
            )
            for item in hit.fired
        ],
        score=ScoreOut(
            total=score.total,
            signals=score.signals,
            trend=score.trend,
            weekly=score.weekly,
            relative_strength=score.relative_strength,
        ),
        risk=RiskOut(
            entry=risk.entry,
            stop=finite(risk.stop),
            targets=[finite(target) for target in risk.targets],
            risk_per_share=finite(risk.risk_per_share),
            size=risk.size,
            position_value=finite(risk.position_value),
            risk_amount=finite(risk.risk_amount),
        ),
        edge=edge_stats_out(hit.edge) if hit.edge else None,
    )


def scan_out(report: ScanReport) -> ScanOut:
    return ScanOut(
        universe=report.universe.name,
        regime=regime_out(report.regime),
        hits=[hit_out(hit, report.scorer) for hit in report.hits],
        missing=report.missing,
        skipped=report.skipped,
        min_score=report.min_score,
        fresh_bars=report.fresh_bars,
        edge_horizon=report.edge_horizon,
    )
