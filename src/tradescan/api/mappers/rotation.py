"""Map a rotation report."""

from __future__ import annotations

from dataclasses import fields

from tradescan.api.mappers.backtest import applied_rule_out, metrics_out, split_out, trade_out
from tradescan.api.mappers.common import day, finite, points
from tradescan.api.mappers.portfolio import contribution_out
from tradescan.api.schemas.backtest import BacktestConfigOut
from tradescan.api.schemas.portfolio import PortfolioTradeOut
from tradescan.api.schemas.rotation import (
    PickOut,
    RotationConfigOut,
    RotationOut,
    RotationPeriodOut,
    RotationStatsOut,
    TargetsOut,
)
from tradescan.backtest.rotation import Targets
from tradescan.backtest.rotation_metrics import RotationMetrics
from tradescan.services.rotation import RotationReport


def rotation_period_out(period: RotationMetrics) -> RotationPeriodOut:
    stats = period.stats
    return RotationPeriodOut(
        metrics=metrics_out(period.metrics),
        stats=RotationStatsOut(
            rebalances=stats.rebalances,
            orders=stats.orders,
            unfilled_orders=stats.unfilled_orders,
            average_holdings=finite(stats.average_holdings),
            max_holdings=stats.max_holdings,
            average_exposure_pct=finite(stats.average_exposure_pct),
            average_safe_pct=finite(stats.average_safe_pct),
            average_cash_pct=finite(stats.average_cash_pct),
            turnover_pct=finite(stats.turnover_pct),
            commissions=stats.commissions,
        ),
    )


def targets_out(targets: Targets) -> TargetsOut:
    return TargetsOut(
        date=day(targets.date),
        picks=[
            PickOut(
                ticker=pick.ticker,
                score=finite(pick.score),
                momentum_pct=finite(pick.momentum * 100.0),
                weight_pct=pick.weight_pct,
                held=pick.held,
            )
            for pick in targets.picks
        ],
        safe_pct=targets.safe_pct,
        cash_pct=targets.cash_pct,
    )


def rotation_out(report: RotationReport) -> RotationOut:
    result, config, rotation = report.result, report.config, report.rotation
    close = report.benchmark_close.dropna()
    buy_hold = close / close.iloc[0] * config.initial_equity if len(close) else close
    return RotationOut(
        universe=report.universe.name,
        engine=result.engine,
        start=day(result.equity.index[0]),
        end=day(result.equity.index[-1]),
        config=BacktestConfigOut(**{item.name: getattr(config, item.name) for item in fields(config)}),
        rotation=RotationConfigOut(
            holdings=rotation.holdings,
            absolute_lookback=rotation.absolute_lookback,
            rebalance=rotation.rebalance,
            safe_asset=rotation.safe_asset,
        ),
        ranking=applied_rule_out(report.ranking),
        weighting=applied_rule_out(report.weighting),
        buy_hold_benchmark=report.benchmark,
        buy_hold=points(buy_hold),
        split=split_out(report.split) if report.split else None,
        full=rotation_period_out(report.full),
        in_sample=rotation_period_out(report.in_sample) if report.in_sample else None,
        out_of_sample=rotation_period_out(report.out_of_sample) if report.out_of_sample else None,
        equity=points(result.equity),
        holdings=points(result.holdings.astype(float)),
        targets=targets_out(result.targets),
        trades=[PortfolioTradeOut(ticker=item.ticker, **trade_out(item.trade).model_dump()) for item in result.trades],
        tickers=[contribution_out(row) for row in report.contributions],
        missing=report.missing,
    )
