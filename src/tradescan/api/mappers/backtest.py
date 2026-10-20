"""Map a backtest report, and the setup, metrics, trades and split the other backtests share."""

from __future__ import annotations

import math
from dataclasses import fields

import pandas as pd

from tradescan.api.mappers.common import day, finite, points, signal_params
from tradescan.api.schemas.backtest import (
    AppliedRuleOut,
    BacktestConfigOut,
    BacktestOut,
    EngineRunOut,
    FillOut,
    MetricsOut,
    MonteCarloMethodOut,
    MonteCarloOut,
    MonteCarloPathOut,
    PercentilesOut,
    SplitOut,
    TradeOut,
)
from tradescan.backtest.base import BacktestConfig, Trade
from tradescan.backtest.metrics import Metrics
from tradescan.backtest.monte_carlo import Distribution, MonteCarlo, PathStats, Percentiles
from tradescan.backtest.oos import Split
from tradescan.backtest.rules import Rule
from tradescan.backtest.trade_rules import TradeRules
from tradescan.services.backtest import BacktestReport
from tradescan.signals.base import Signal


def applied_rule_out(rule: Rule) -> AppliedRuleOut:
    return AppliedRuleOut(name=rule.name, label=rule.label, description=rule.describe(), params=signal_params(rule))


def metrics_out(metrics: Metrics) -> MetricsOut:
    values = {item.name: getattr(metrics, item.name) for item in fields(metrics)}
    floats = {name: finite(value) for name, value in values.items() if name != "trades"}
    return MetricsOut(
        **floats,
        trades=metrics.trades,
        profit_factor_infinite=math.isinf(metrics.profit_factor),
    )


def trade_out(trade: Trade) -> TradeOut:
    return TradeOut(
        direction=trade.direction,
        signal_date=day(trade.signal_date),
        entry_date=day(trade.entry_date),
        exit_date=day(trade.exit_date),
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        size=trade.size,
        pnl=trade.pnl,
        r_multiple=finite(trade.r_multiple),
        exit_reason=trade.exit_reason,
        adds=[FillOut(date=day(fill.date), price=fill.price) for fill in trade.adds],
    )


def percentiles_out(percentiles: Percentiles) -> PercentilesOut:
    return PercentilesOut(**{item.name: finite(getattr(percentiles, item.name)) for item in fields(percentiles)})


def path_out(path: PathStats) -> MonteCarloPathOut:
    return MonteCarloPathOut(
        final_return_pct=finite(path.final_return_pct),
        max_drawdown_pct=finite(path.max_drawdown_pct),
        longest_losing_streak=path.longest_losing_streak,
    )


def distribution_out(distribution: Distribution) -> MonteCarloMethodOut:
    method = distribution.method
    return MonteCarloMethodOut(
        name=method.name,
        label=method.label,
        description=method.description,
        final_return_pct=percentiles_out(distribution.final_return_pct),
        max_drawdown_pct=percentiles_out(distribution.max_drawdown_pct),
        longest_losing_streak=percentiles_out(distribution.longest_losing_streak),
        ruin_pct=distribution.ruin_pct,
    )


def monte_carlo_out(monte_carlo: MonteCarlo) -> MonteCarloOut:
    config = monte_carlo.config
    return MonteCarloOut(
        simulations=config.simulations,
        ruin_drawdown_pct=config.ruin_drawdown_pct,
        seed=config.seed,
        risk_pct=monte_carlo.risk_pct,
        trades=monte_carlo.trades,
        actual=path_out(monte_carlo.actual),
        methods=[distribution_out(distribution) for distribution in monte_carlo.methods],
    )


def setup_out(
    ticker: str, signal: Signal, config: BacktestConfig, rules: TradeRules, benchmark: str | None, close: pd.Series
) -> dict[str, object]:
    """The fields a backtest and a sweep share: what was tested, on which data, with which rules."""
    return {
        "ticker": ticker,
        "start": day(close.index[0]),
        "end": day(close.index[-1]),
        **rules_out(signal, config, rules, benchmark),
    }


def rules_out(signal: Signal, config: BacktestConfig, rules: TradeRules, benchmark: str | None) -> dict[str, object]:
    """What was tested apart from the ticker: the signal, the settings and the rules."""
    return {
        "signal": signal.name,
        "direction": signal.direction,
        "description": signal.describe(),
        "params": signal_params(signal),
        "config": BacktestConfigOut(**{item.name: getattr(config, item.name) for item in fields(config)}),
        "entry": applied_rule_out(rules.entry),
        "exits": [applied_rule_out(rule) for rule in rules.exits],
        "filters": [applied_rule_out(rule) for rule in rules.filters],
        "benchmark": benchmark,
    }


def split_out(split: Split) -> SplitOut:
    return SplitOut(
        oos_pct=split.oos_pct,
        in_sample_start=day(split.in_sample[0]),
        in_sample_end=day(split.in_sample[1]),
        out_of_sample_start=day(split.out_of_sample[0]),
        out_of_sample_end=day(split.out_of_sample[1]),
    )


def backtest_out(report: BacktestReport) -> BacktestOut:
    close = report.close
    buy_hold = close / close.iloc[0] * report.config.initial_equity
    return BacktestOut(
        **setup_out(report.ticker, report.signal, report.config, report.rules, report.benchmark, close),
        split=split_out(report.split) if report.split else None,
        buy_hold=points(buy_hold),
        runs=[
            EngineRunOut(
                engine=run.result.engine,
                metrics=metrics_out(run.metrics),
                in_sample=metrics_out(run.periods.in_sample) if run.periods else None,
                out_of_sample=metrics_out(run.periods.out_of_sample) if run.periods else None,
                monte_carlo=monte_carlo_out(run.monte_carlo) if run.monte_carlo else None,
                equity=points(run.result.equity),
                trades=[trade_out(trade) for trade in run.result.trades],
            )
            for run in report.runs
        ],
    )
