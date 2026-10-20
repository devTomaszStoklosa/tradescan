"""Map an edge report, and the edge statistics a scan reports per hit too."""

from __future__ import annotations

from tradescan.api.mappers.common import finite
from tradescan.api.schemas.edge import EdgeOut, EdgeRowOut, EdgeStatsOut
from tradescan.backtest.edge import EdgeStats
from tradescan.services.edge import EdgeReport


def edge_stats_out(stats: EdgeStats) -> EdgeStatsOut:
    return EdgeStatsOut(
        signal=stats.signal,
        horizon=stats.horizon,
        events=stats.events,
        win_rate=finite(stats.win_rate),
        mean_return=finite(stats.mean_return),
        median_return=finite(stats.median_return),
        baseline_return=finite(stats.baseline_return),
        edge=finite(stats.edge),
    )


def edge_out(report: EdgeReport) -> EdgeOut:
    return EdgeOut(
        universe=report.universe.name,
        horizons=list(report.horizons),
        tickers=report.tickers,
        rows=[
            EdgeRowOut(
                signal=row.signal.name,
                family=row.signal.family,
                direction=row.signal.direction,
                description=row.signal.describe(),
                stats=[edge_stats_out(stats) for stats in row.stats],
            )
            for row in report.rows
        ],
        missing=report.missing,
    )
