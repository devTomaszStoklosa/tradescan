"""Map a portfolio report, and the contributions a rotation reports too."""

from __future__ import annotations

from tradescan.api.mappers.backtest import applied_rule_out, metrics_out, rules_out, split_out, trade_out
from tradescan.api.mappers.common import day, finite, points, serializable, signal_params
from tradescan.api.schemas.portfolio import (
    PortfolioConfigOut,
    PortfolioOut,
    PortfolioPeriodOut,
    PortfolioRunOut,
    PortfolioStatsOut,
    PortfolioTradeOut,
    ScanInputsOut,
    TickerContributionOut,
)
from tradescan.backtest.portfolio_metrics import PortfolioMetrics, TickerContribution
from tradescan.services.portfolio import PortfolioReport, ScanInputs


def portfolio_period_out(period: PortfolioMetrics) -> PortfolioPeriodOut:
    stats = period.stats
    return PortfolioPeriodOut(
        metrics=metrics_out(period.metrics),
        stats=PortfolioStatsOut(
            average_positions=finite(stats.average_positions),
            max_positions=stats.max_positions,
            average_exposure_pct=finite(stats.average_exposure_pct),
            max_exposure_pct=finite(stats.max_exposure_pct),
            orders=stats.orders,
            skipped_no_slot=stats.skipped_no_slot,
            skipped_no_room=stats.skipped_no_room,
        ),
    )


def contribution_out(row: TickerContribution) -> TickerContributionOut:
    return TickerContributionOut(
        ticker=row.ticker,
        trades=row.trades,
        pnl=row.pnl,
        contribution_pct=finite(row.contribution_pct),
        win_rate_pct=finite(row.win_rate_pct),
        expectancy_r=finite(row.expectancy_r),
    )


def scan_inputs_out(scan: ScanInputs) -> ScanInputsOut:
    return ScanInputsOut(
        settings={
            section: {name: serializable(value) for name, value in values.items()}
            for section, values in scan.settings.items()
        },
        signal_params={signal.name: signal_params(signal) for signal in scan.signals},
    )


def portfolio_out(report: PortfolioReport) -> PortfolioOut:
    base = report.base
    close = report.benchmark_close.dropna()
    buy_hold = close / close.iloc[0] * base.config.initial_equity if len(close) else close
    return PortfolioOut(
        **rules_out(base.signal, base.config, base.rules, base.benchmark),
        universe=report.universe.name,
        start=day(report.calendar[0]),
        end=day(report.calendar[-1]),
        portfolio=PortfolioConfigOut(
            max_positions=report.portfolio.max_positions, max_exposure_pct=report.portfolio.max_exposure_pct
        ),
        priority=applied_rule_out(report.priority),
        scan=scan_inputs_out(report.scan) if report.scan else None,
        buy_hold_benchmark=report.benchmark,
        buy_hold=points(buy_hold),
        split=split_out(report.split) if report.split else None,
        runs=[
            PortfolioRunOut(
                engine=run.result.engine,
                full=portfolio_period_out(run.full),
                in_sample=portfolio_period_out(run.in_sample) if run.in_sample else None,
                out_of_sample=portfolio_period_out(run.out_of_sample) if run.out_of_sample else None,
                equity=points(run.result.equity),
                positions=points(run.result.positions.astype(float)),
                trades=[
                    PortfolioTradeOut(ticker=item.ticker, **trade_out(item.trade).model_dump())
                    for item in run.result.trades
                ],
                tickers=[contribution_out(row) for row in run.contributions],
            )
            for run in report.runs
        ],
        missing=report.missing,
    )
